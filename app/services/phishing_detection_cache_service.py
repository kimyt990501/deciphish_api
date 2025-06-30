from app.core.database import async_session
from app.core.config import settings
from datetime import datetime, timedelta
import logging
import hashlib
import json
from sqlalchemy import text

logger = logging.getLogger(__name__)

class PhishingDetectionCacheService:
    """피싱 검사 결과 캐싱 서비스"""
    
    def __init__(self, cache_ttl_hours: int = None):
        """
        Args:
            cache_ttl_hours: 캐시 유효 시간 (시간 단위, 기본값은 설정에서 가져옴)
        """
        self.cache_ttl_hours = cache_ttl_hours or settings.CACHE_TTL_HOURS
    
    def _get_url_hash(self, url: str) -> str:
        """URL을 해시화하여 키로 사용"""
        return hashlib.md5(url.encode('utf-8')).hexdigest()
    
    async def get_cached_result(self, url: str) -> dict:
        """
        캐시된 피싱 검사 결과 조회
        
        Args:
            url: 검사할 URL
            
        Returns:
            캐시된 결과 또는 None
        """
        try:
            async with async_session() as session:
                # TTL 체크 포함하여 조회
                cutoff_time = datetime.now() - timedelta(hours=self.cache_ttl_hours)
                
                query = text("""
                SELECT url, is_phish, reason, detected_brand, confidence, created_at, screenshot_base64
                FROM phishing_detections 
                WHERE url = :url AND created_at > :cutoff_time
                ORDER BY created_at DESC 
                LIMIT 1
                """)
                
                result = await session.execute(query, {"url": url, "cutoff_time": cutoff_time})
                row = result.fetchone()
                
                if row:
                    logger.info(f"캐시된 결과 조회 성공: {url}")
                    result_dict = {
                        "url": row[0],
                        "is_phish": row[1],
                        "reason": row[2],
                        "detected_brand": row[3],
                        "confidence": row[4],
                        "cached_at": row[5].isoformat(),
                        "from_cache": True
                    }
                    
                    # 스크린샷이 있으면 포함
                    if row[6]:  # screenshot_base64
                        result_dict["screenshot_base64"] = row[6]
                        result_dict["has_screenshot"] = True
                        result_dict["screenshot_size"] = len(row[6])
                    else:
                        result_dict["has_screenshot"] = False
                    
                    return result_dict
                else:
                    logger.info(f"캐시된 결과 없음: {url}")
                    return None
                        
        except Exception as e:
            logger.error(f"캐시 조회 실패: {e}")
            return None
    
    async def save_detection_result(self, url: str, html_content: str, favicon_base64: str, 
                                  detection_result: dict, user_id: int = None, ip_address: str = None, user_agent: str = None, screenshot_base64: str = None) -> bool:
        """
        피싱 검사 결과를 데이터베이스에 저장
        
        Args:
            url: 검사한 URL (최종 URL)
            html_content: HTML 내용
            favicon_base64: 파비콘 Base64
            detection_result: 검사 결과 (original_url, final_url 정보 포함 가능)
            user_id: 사용자 ID (선택적)
            ip_address: IP 주소 (선택적)
            user_agent: User Agent (선택적)
            
        Returns:
            저장 성공 여부
        """
        try:
            async with async_session() as session:
                # 리다이렉트 정보 추출
                original_url = detection_result.get("original_url", url)
                final_url = detection_result.get("final_url", url)
                redirect_analysis = detection_result.get("redirect_analysis", {})
                
                # 리다이렉트가 발생한 경우 원본 URL을 저장, 아니면 최종 URL 저장
                url_to_store = original_url if redirect_analysis.get("has_redirect", False) else final_url
                
                # 디버깅 로그 추가
                if redirect_analysis.get("has_redirect", False):
                    print(f"리다이렉트 케이스 - 원본 URL 저장: {original_url}")
                    print(f"   최종 URL: {final_url}")
                else:
                    print(f"일반 케이스 - URL 저장: {url_to_store}")
                
                # 리다이렉트 정보를 reason에 포함 (총 200자 제한)
                reason = detection_result.get("reason", "")
                if redirect_analysis.get("has_redirect", False):
                    if original_url != final_url:
                        # 더 짧게 자르고 총 길이도 제한
                        short_final_url = final_url[:50] + "..." if len(final_url) > 50 else final_url
                        redirect_text = f" (redirected to {short_final_url})"
                        # 전체 reason이 200자를 넘지 않도록 조정
                        max_reason_length = 200 - len(redirect_text)
                        if len(reason) > max_reason_length:
                            reason = reason[:max_reason_length]
                        reason += redirect_text
                
                query = text("""
                INSERT INTO phishing_detections 
                (user_id, url, is_phish, reason, detected_brand, confidence, html_content, favicon_base64, screenshot_base64, ip_address, user_agent, is_redirect, redirect_url, is_crp)
                VALUES (:user_id, :url, :is_phish, :reason, :detected_brand, :confidence, :html_content, :favicon_base64, :screenshot_base64, :ip_address, :user_agent, :is_redirect, :redirect_url, :is_crp)
                """)
                
                # 새로운 칼럼들 값 계산
                is_redirect = 1 if redirect_analysis.get("has_redirect", False) else 0
                redirect_url = final_url if redirect_analysis.get("has_redirect", False) else None
                is_crp = 1 if detection_result.get("crp_detected", False) else 0
                
                values = {
                    "user_id": user_id,
                    "url": url_to_store,  # 리다이렉트 시 원본 URL, 아니면 최종 URL 저장
                    "is_phish": detection_result.get("is_phish", 0),
                    "reason": reason[:250] if reason else "",  # reason도 250자로 제한
                    "detected_brand": detection_result.get("detected_brand", "")[:100] if detection_result.get("detected_brand") else "",  # 브랜드명도 제한
                    "confidence": detection_result.get("similarity", detection_result.get("confidence", 0.0)),
                    "html_content": html_content[:65535] if html_content else "",  # TEXT 크기 제한
                    "favicon_base64": favicon_base64[:65535] if favicon_base64 else "",  # TEXT 크기 제한
                    "screenshot_base64": screenshot_base64 if screenshot_base64 else "",  # 스크린샷 Base64
                    "ip_address": ip_address,
                    "user_agent": user_agent[:1000] if user_agent else None,  # 크기 제한
                    "is_redirect": is_redirect,
                    "redirect_url": redirect_url,  # TEXT 컬럼으로 변경했으므로 크기 제한 제거
                    "is_crp": is_crp
                }
                
                print(f"DB 저장 시작 - URL: {url_to_store}")
                print(f"   is_redirect: {is_redirect}, redirect_url: {redirect_url}")
                print(f"   is_crp: {is_crp}")
                print(f"   has_screenshot: {len(screenshot_base64) > 0 if screenshot_base64 else False}")
                await session.execute(query, values)
                await session.commit()
                print(f"DB 저장 완료 - URL: {url_to_store}")
                
                if redirect_analysis.get("has_redirect", False):
                    redirect_msg = f" (원본 URL 저장: {original_url} -> {final_url})"
                else:
                    redirect_msg = ""
                
                crp_msg = f" CRP: {'검출' if is_crp else '미검출'}"
                logger.info(f"검사 결과 저장 성공: {url_to_store} - {detection_result.get('reason', '')} (사용자: {user_id}){redirect_msg}{crp_msg}")
                return True
                    
        except Exception as e:
            print(f"DB 저장 실패 - URL: {url}")
            print(f"   오류: {str(e)}")
            print(f"   detection_result: {detection_result}")
            logger.error(f"검사 결과 저장 실패: {e}")
            return False
    
    async def get_cache_stats(self) -> dict:
        """캐시 통계 정보 조회"""
        try:
            async with async_session() as session:
                # 전체 레코드 수
                result = await session.execute(text("SELECT COUNT(*) FROM phishing_detections"))
                total_records = result.fetchone()[0]
                
                # 최근 24시간 레코드 수
                cutoff_time = datetime.now() - timedelta(hours=24)
                result = await session.execute(
                    text("SELECT COUNT(*) FROM phishing_detections WHERE created_at > :cutoff_time"), 
                    {"cutoff_time": cutoff_time}
                )
                recent_records = result.fetchone()[0]
                
                # 피싱/정상 분포
                result = await session.execute(
                    text("SELECT is_phish, COUNT(*) FROM phishing_detections GROUP BY is_phish")
                )
                phish_stats = result.fetchall()
                
                stats = {
                    "total_records": total_records,
                    "recent_24h_records": recent_records,
                    "cache_ttl_hours": self.cache_ttl_hours,
                    "phishing_count": 0,
                    "legitimate_count": 0
                }
                
                for is_phish, count in phish_stats:
                    if is_phish == 1:
                        stats["phishing_count"] = count
                    else:
                        stats["legitimate_count"] = count
                
                return stats
                    
        except Exception as e:
            logger.error(f"캐시 통계 조회 실패: {e}")
            return {"error": str(e)}
    
    async def clear_expired_cache(self) -> int:
        """만료된 캐시 항목 삭제"""
        try:
            async with async_session() as session:
                cutoff_time = datetime.now() - timedelta(hours=self.cache_ttl_hours)
                
                result = await session.execute(
                    text("DELETE FROM phishing_detections WHERE created_at < :cutoff_time"), 
                    {"cutoff_time": cutoff_time}
                )
                deleted_count = result.rowcount
                await session.commit()
                
                logger.info(f"만료된 캐시 {deleted_count}개 항목 삭제")
                return deleted_count
                    
        except Exception as e:
            logger.error(f"만료된 캐시 삭제 실패: {e}")
            return 0
    
    async def get_user_detection_history(self, user_id: int, url: str = None, limit: int = 50, offset: int = 0) -> dict:
        """
        사용자별 검사 기록 조회
        
        Args:
            user_id: 사용자 ID
            url: 특정 URL 필터 (None이면 전체 조회)
            limit: 조회할 레코드 수 (최대 100)
            offset: 시작 위치
            
        Returns:
            사용자의 검사 기록 및 메타데이터
        """
        try:
            limit = min(limit, 100)  # 최대 100개로 제한
            
            async with async_session() as session:
                # 기본 쿼리 - 해당 사용자의 기록만
                base_query = """
                SELECT url, is_phish, reason, detected_brand, confidence, created_at, updated_at
                FROM phishing_detections
                WHERE user_id = :user_id
                """
                count_query = "SELECT COUNT(*) FROM phishing_detections WHERE user_id = :user_id"
                
                # URL 필터 적용
                params = {"user_id": user_id}
                if url:
                    base_query += " AND url = :url"
                    count_query += " AND url = :url"
                    params["url"] = url
                
                # 정렬 및 페이징
                base_query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                params.update({"limit": limit, "offset": offset})
                
                # 데이터 조회
                result = await session.execute(text(base_query), params)
                records = result.fetchall()
                
                # 전체 개수 조회
                count_params = {"user_id": user_id}
                if url:
                    count_params["url"] = url
                count_result = await session.execute(text(count_query), count_params)
                total_count = count_result.fetchone()[0]
                
                # 결과 구성
                history = []
                for record in records:
                    history.append({
                        "url": record[0],
                        "is_phish": record[1],
                        "reason": record[2],
                        "detected_brand": record[3],
                        "confidence": record[4],
                        "created_at": record[5].isoformat() if record[5] else None,
                        "updated_at": record[6].isoformat() if record[6] else None
                    })
                
                return {
                    "total_count": total_count,
                    "returned_count": len(history),
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + len(history) < total_count,
                    "history": history
                }
                
        except Exception as e:
            logger.error(f"사용자 검사 기록 조회 실패: {e}")
            return {"error": str(e)}

    async def get_user_detection_statistics(self, user_id: int, days: int = 7) -> dict:
        """
        사용자별 검사 통계 정보 조회
        
        Args:
            user_id: 사용자 ID
            days: 통계 기간 (일 단위)
            
        Returns:
            사용자의 검사 통계 정보
        """
        try:
            async with async_session() as session:
                cutoff_time = datetime.now() - timedelta(days=days)
                
                # 사용자별 전체 통계
                total_result = await session.execute(
                    text("SELECT COUNT(*), SUM(is_phish), AVG(confidence) FROM phishing_detections WHERE user_id = :user_id AND created_at > :cutoff_time"),
                    {"user_id": user_id, "cutoff_time": cutoff_time}
                )
                total_stats = total_result.fetchone()
                
                # 사용자별 브랜드 통계
                brand_result = await session.execute(
                    text("""
                    SELECT detected_brand, COUNT(*), SUM(is_phish) 
                    FROM phishing_detections 
                    WHERE user_id = :user_id AND created_at > :cutoff_time AND detected_brand IS NOT NULL AND detected_brand != ''
                    GROUP BY detected_brand 
                    ORDER BY COUNT(*) DESC 
                    LIMIT 10
                    """),
                    {"user_id": user_id, "cutoff_time": cutoff_time}
                )
                brand_stats = brand_result.fetchall()
                
                # 사용자별 일별 통계
                daily_result = await session.execute(
                    text("""
                    SELECT DATE(created_at) as date, COUNT(*), SUM(is_phish)
                    FROM phishing_detections 
                    WHERE user_id = :user_id AND created_at > :cutoff_time
                    GROUP BY DATE(created_at) 
                    ORDER BY date DESC
                    """),
                    {"user_id": user_id, "cutoff_time": cutoff_time}
                )
                daily_stats = daily_result.fetchall()
                
                return {
                    "period_days": days,
                    "total_detections": total_stats[0] if total_stats[0] else 0,
                    "phishing_count": int(total_stats[1]) if total_stats[1] else 0,
                    "legitimate_count": int(total_stats[0] - (total_stats[1] or 0)) if total_stats[0] else 0,
                    "average_confidence": float(total_stats[2]) if total_stats[2] else 0.0,
                    "top_brands": [
                        {
                            "brand": brand[0],
                            "total_count": brand[1],
                            "phishing_count": int(brand[2])
                        }
                        for brand in brand_stats
                    ],
                    "daily_stats": [
                        {
                            "date": daily[0].isoformat(),
                            "total_count": daily[1],
                            "phishing_count": int(daily[2])
                        }
                        for daily in daily_stats
                    ]
                }
                
        except Exception as e:
            logger.error(f"사용자 검사 통계 조회 실패: {e}")
            return {"error": str(e)}

    async def get_detection_history(self, url: str = None, limit: int = 50, offset: int = 0) -> dict:
        """
        검사 기록 조회
        
        Args:
            url: 특정 URL 필터 (None이면 전체 조회)
            limit: 조회할 레코드 수 (최대 100)
            offset: 시작 위치
            
        Returns:
            검사 기록 및 메타데이터
        """
        try:
            limit = min(limit, 100)  # 최대 100개로 제한
            
            async with async_session() as session:
                # 기본 쿼리
                base_query = """
                SELECT url, is_phish, reason, detected_brand, confidence, created_at, updated_at
                FROM phishing_detections
                """
                count_query = "SELECT COUNT(*) FROM phishing_detections"
                
                # URL 필터 적용
                params = {}
                if url:
                    base_query += " WHERE url = :url"
                    count_query += " WHERE url = :url"
                    params["url"] = url
                
                # 정렬 및 페이징
                base_query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                params.update({"limit": limit, "offset": offset})
                
                # 데이터 조회
                result = await session.execute(text(base_query), params)
                records = result.fetchall()
                
                # 전체 개수 조회
                if url:
                    count_result = await session.execute(text(count_query), {"url": url})
                else:
                    count_result = await session.execute(text(count_query))
                total_count = count_result.fetchone()[0]
                
                # 결과 구성
                history = []
                for record in records:
                    history.append({
                        "url": record[0],
                        "is_phish": record[1],
                        "reason": record[2],
                        "detected_brand": record[3],
                        "confidence": record[4],
                        "created_at": record[5].isoformat() if record[5] else None,
                        "updated_at": record[6].isoformat() if record[6] else None
                    })
                
                return {
                    "total_count": total_count,
                    "returned_count": len(history),
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + len(history) < total_count,
                    "history": history
                }
                
        except Exception as e:
            logger.error(f"검사 기록 조회 실패: {e}")
            return {"error": str(e)}
    
    async def get_detection_statistics(self, days: int = 7) -> dict:
        """
        검사 통계 정보 조회
        
        Args:
            days: 통계 기간 (일 단위)
            
        Returns:
            검사 통계 정보
        """
        try:
            async with async_session() as session:
                cutoff_time = datetime.now() - timedelta(days=days)
                
                # 전체 통계
                total_result = await session.execute(
                    text("SELECT COUNT(*), SUM(is_phish), AVG(confidence) FROM phishing_detections WHERE created_at > :cutoff_time"),
                    {"cutoff_time": cutoff_time}
                )
                total_stats = total_result.fetchone()
                
                # 브랜드별 통계
                brand_result = await session.execute(
                    text("""
                    SELECT detected_brand, COUNT(*), SUM(is_phish) 
                    FROM phishing_detections 
                    WHERE created_at > :cutoff_time AND detected_brand IS NOT NULL AND detected_brand != ''
                    GROUP BY detected_brand 
                    ORDER BY COUNT(*) DESC 
                    LIMIT 10
                    """),
                    {"cutoff_time": cutoff_time}
                )
                brand_stats = brand_result.fetchall()
                
                # 이유별 통계
                reason_result = await session.execute(
                    text("""
                    SELECT reason, COUNT(*) 
                    FROM phishing_detections 
                    WHERE created_at > :cutoff_time
                    GROUP BY reason 
                    ORDER BY COUNT(*) DESC
                    """),
                    {"cutoff_time": cutoff_time}
                )
                reason_stats = reason_result.fetchall()
                
                # 일별 통계
                daily_result = await session.execute(
                    text("""
                    SELECT DATE(created_at) as date, COUNT(*), SUM(is_phish)
                    FROM phishing_detections 
                    WHERE created_at > :cutoff_time
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                    """),
                    {"cutoff_time": cutoff_time}
                )
                daily_stats = daily_result.fetchall()
                
                return {
                    "period_days": days,
                    "period_start": cutoff_time.isoformat(),
                    "period_end": datetime.now().isoformat(),
                    "summary": {
                        "total_detections": total_stats[0] if total_stats[0] else 0,
                        "phishing_detections": total_stats[1] if total_stats[1] else 0,
                        "legitimate_detections": (total_stats[0] - total_stats[1]) if total_stats[0] and total_stats[1] else 0,
                        "average_confidence": float(total_stats[2]) if total_stats[2] else 0.0,
                        "phishing_rate": float(total_stats[1] / total_stats[0]) if total_stats[0] and total_stats[1] else 0.0
                    },
                    "top_brands": [
                        {
                            "brand": brand[0],
                            "total_detections": brand[1],
                            "phishing_detections": brand[2],
                            "phishing_rate": float(brand[2] / brand[1]) if brand[1] else 0.0
                        }
                        for brand in brand_stats
                    ],
                    "detection_reasons": [
                        {
                            "reason": reason[0],
                            "count": reason[1]
                        }
                        for reason in reason_stats
                    ],
                    "daily_stats": [
                        {
                            "date": daily[0].isoformat() if daily[0] else None,
                            "total_detections": daily[1],
                            "phishing_detections": daily[2]
                        }
                        for daily in daily_stats
                    ]
                }
                
        except Exception as e:
            logger.error(f"검사 통계 조회 실패: {e}")
            return {"error": str(e)}
    
    async def search_detections(self, 
                              is_phish: int = None,
                              detected_brand: str = None,
                              reason: str = None,
                              start_date: datetime = None,
                              end_date: datetime = None,
                              limit: int = 50,
                              offset: int = 0) -> dict:
        """
        검사 결과 검색
        
        Args:
            is_phish: 피싱 여부 필터 (0, 1, None)
            detected_brand: 브랜드 필터
            reason: 판단 이유 필터
            start_date: 시작 날짜
            end_date: 종료 날짜
            limit: 조회할 레코드 수
            offset: 시작 위치
            
        Returns:
            검색 결과
        """
        try:
            limit = min(limit, 100)  # 최대 100개로 제한
            
            async with async_session() as session:
                # 동적 쿼리 구성
                where_clauses = []
                params = {"limit": limit, "offset": offset}
                
                if is_phish is not None:
                    where_clauses.append("is_phish = :is_phish")
                    params["is_phish"] = is_phish
                
                if detected_brand:
                    where_clauses.append("detected_brand LIKE :detected_brand")
                    params["detected_brand"] = f"%{detected_brand}%"
                
                if reason:
                    where_clauses.append("reason LIKE :reason")
                    params["reason"] = f"%{reason}%"
                
                if start_date:
                    where_clauses.append("created_at >= :start_date")
                    params["start_date"] = start_date
                
                if end_date:
                    where_clauses.append("created_at <= :end_date")
                    params["end_date"] = end_date
                
                # 쿼리 완성
                base_query = """
                SELECT url, is_phish, reason, detected_brand, confidence, created_at, updated_at
                FROM phishing_detections
                """
                count_query = "SELECT COUNT(*) FROM phishing_detections"
                
                if where_clauses:
                    where_clause = " WHERE " + " AND ".join(where_clauses)
                    base_query += where_clause
                    count_query += where_clause
                
                base_query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                
                # 데이터 조회
                result = await session.execute(text(base_query), params)
                records = result.fetchall()
                
                # 전체 개수 조회
                count_params = {k: v for k, v in params.items() if k not in ["limit", "offset"]}
                count_result = await session.execute(text(count_query), count_params)
                total_count = count_result.fetchone()[0]
                
                # 결과 구성
                results = []
                for record in records:
                    results.append({
                        "url": record[0],
                        "is_phish": record[1],
                        "reason": record[2],
                        "detected_brand": record[3],
                        "confidence": record[4],
                        "created_at": record[5].isoformat() if record[5] else None,
                        "updated_at": record[6].isoformat() if record[6] else None
                    })
                
                return {
                    "total_count": total_count,
                    "returned_count": len(results),
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + len(results) < total_count,
                    "filters": {
                        "is_phish": is_phish,
                        "detected_brand": detected_brand,
                        "reason": reason,
                        "start_date": start_date.isoformat() if start_date else None,
                        "end_date": end_date.isoformat() if end_date else None
                    },
                    "results": results
                }
                
        except Exception as e:
            logger.error(f"검사 결과 검색 실패: {e}")
            return {"error": str(e)}
    
    async def get_screenshot_by_detection_id(self, detection_id: int, user_id: int = None, is_admin: bool = False) -> dict:
        """탐지 ID로 스크린샷 조회"""
        try:
            async with async_session() as session:
                if is_admin:
                    # 관리자는 모든 스크린샷 조회 가능
                    query = text("""
                    SELECT id, url, screenshot_base64, detected_brand, is_phish, created_at
                    FROM phishing_detections 
                    WHERE id = :detection_id AND screenshot_base64 IS NOT NULL AND screenshot_base64 != ''
                    """)
                    params = {"detection_id": detection_id}
                else:
                    # 일반 사용자는 자신의 탐지 결과만 조회 가능
                    query = text("""
                    SELECT id, url, screenshot_base64, detected_brand, is_phish, created_at
                    FROM phishing_detections 
                    WHERE id = :detection_id AND (user_id = :user_id OR user_id IS NULL) 
                    AND screenshot_base64 IS NOT NULL AND screenshot_base64 != ''
                    """)
                    params = {"detection_id": detection_id, "user_id": user_id}
                
                result = await session.execute(query, params)
                row = result.fetchone()
                
                if row:
                    return {
                        "id": row[0],
                        "url": row[1],
                        "screenshot_base64": row[2],
                        "detected_brand": row[3],
                        "is_phish": row[4],
                        "created_at": row[5]
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"탐지 ID 기반 스크린샷 조회 실패: {e}")
            return None
    
    async def get_screenshot_by_url(self, url: str, user_id: int = None, is_admin: bool = False) -> dict:
        """URL로 최신 스크린샷 조회"""
        try:
            async with async_session() as session:
                if is_admin:
                    # 관리자는 모든 스크린샷 조회 가능
                    query = text("""
                    SELECT id, url, screenshot_base64, detected_brand, is_phish, created_at
                    FROM phishing_detections 
                    WHERE url = :url AND screenshot_base64 IS NOT NULL AND screenshot_base64 != ''
                    ORDER BY created_at DESC
                    LIMIT 1
                    """)
                    params = {"url": url}
                else:
                    # 일반 사용자는 자신의 탐지 결과만 조회 가능
                    query = text("""
                    SELECT id, url, screenshot_base64, detected_brand, is_phish, created_at
                    FROM phishing_detections 
                    WHERE url = :url AND (user_id = :user_id OR user_id IS NULL)
                    AND screenshot_base64 IS NOT NULL AND screenshot_base64 != ''
                    ORDER BY created_at DESC
                    LIMIT 1
                    """)
                    params = {"url": url, "user_id": user_id}
                
                result = await session.execute(query, params)
                row = result.fetchone()
                
                if row:
                    return {
                        "id": row[0],
                        "url": row[1],
                        "screenshot_base64": row[2],
                        "detected_brand": row[3],
                        "is_phish": row[4],
                        "created_at": row[5]
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"URL 기반 스크린샷 조회 실패: {e}")
            return None

# 전역 캐시 서비스 인스턴스
phishing_cache_service = PhishingDetectionCacheService() 