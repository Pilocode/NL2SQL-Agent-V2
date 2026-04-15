from __future__ import annotations

import re

from core.models import ExampleCandidate, QueryAnalysis, RetrievalHit, SQLDraft, SemanticInterpretation


KEYWORD_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+")
CHINESE_NUMBER_MAP = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


class SQLGenerator:
    def __init__(self, demo_questions: tuple[ExampleCandidate, ...], database_id: str = "chinook"):
        self.demo_questions = demo_questions
        self.database_id = database_id

    def generate(
        self,
        question: str,
        analysis: QueryAnalysis,
        retrievals: tuple[RetrievalHit, ...],
        example_candidates: tuple[ExampleCandidate, ...],
        prompt: str,
        semantic_interpretation: SemanticInterpretation | None = None,
    ) -> SQLDraft | None:
        effective_question = semantic_interpretation.rewritten_question if semantic_interpretation is not None else question
        matched_example = self._select_best_example(effective_question, example_candidates)
        if matched_example is not None and self._score_example(effective_question, matched_example) >= 12:
            return SQLDraft(
                sql=matched_example.sql,
                source="example_reuse",
                rationale=f"复用高匹配演示问题: {matched_example.question}",
                prompt=prompt,
            )

        rule_based_sql, source, rationale = self._generate_from_rules(effective_question, analysis, retrievals, semantic_interpretation)
        if rule_based_sql is not None:
            return SQLDraft(
                sql=rule_based_sql,
                source=source,
                rationale=rationale,
                prompt=prompt,
            )

        if matched_example is not None:
            return SQLDraft(
                sql=matched_example.sql,
                source="example_fallback",
                rationale=f"未命中规则，退回到最相近演示问题: {matched_example.question}",
                prompt=prompt,
            )

        return None

    def _generate_from_rules(
        self,
        question: str,
        analysis: QueryAnalysis,
        retrievals: tuple[RetrievalHit, ...],
        semantic_interpretation: SemanticInterpretation | None = None,
    ) -> tuple[str | None, str, str]:
        if self.database_id != "chinook":
            return None, "unsupported", "当前数据库未配置规则模板，等待 LLM 或 example RAG 生成。"

        normalized = analysis.normalized_question
        rewritten_question = semantic_interpretation.rewritten_question.lower() if semantic_interpretation is not None else ""
        effective_normalized = rewritten_question or normalized
        table_names = {hit.table_name for hit in retrievals}
        limit = analysis.top_k or self._extract_limit(question)
        year = self._extract_year(question)

        if (
            {"Customer", "Invoice"}.issubset(table_names)
            and self._contains_any(effective_normalized, ("客户", "顾客", "用户"))
            and self._contains_any(effective_normalized, ("消费", "销售额", "花费", "金额", "总额"))
        ):
            return (
                "SELECT c.CustomerId, c.FirstName || ' ' || c.LastName AS CustomerName, "
                "ROUND(SUM(i.Total), 2) AS TotalSpent "
                "FROM Customer c "
                "JOIN Invoice i ON c.CustomerId = i.CustomerId "
                "GROUP BY c.CustomerId, CustomerName "
                f"ORDER BY TotalSpent DESC LIMIT {limit or 5};",
                "rule:customer_spend_ranking",
                "识别为客户消费排行问题，使用 Customer 与 Invoice 的聚合模板。",
            )

        if (
            "Invoice" in table_names
            and self._contains_any(effective_normalized, ("国家", "地区"))
            and self._contains_any(effective_normalized, ("销售额", "消费", "总额", "收入"))
        ):
            return (
                "SELECT BillingCountry, ROUND(SUM(Total), 2) AS Revenue "
                "FROM Invoice "
                "GROUP BY BillingCountry "
                f"ORDER BY Revenue DESC LIMIT {limit or 5};",
                "rule:country_revenue_ranking",
                "识别为国家销售排行问题，使用 Invoice 金额聚合模板。",
            )

        if (
            "Customer" in table_names
            and self._contains_any(effective_normalized, ("国家", "地区"))
            and self._contains_any(effective_normalized, ("客户", "顾客", "用户"))
            and self._contains_any(effective_normalized, ("多少", "数量", "最多", "前", "top"))
        ):
            return (
                "SELECT Country, COUNT(*) AS CustomerCount "
                "FROM Customer "
                "WHERE Country IS NOT NULL "
                "GROUP BY Country "
                f"ORDER BY CustomerCount DESC LIMIT {limit or 5};",
                "rule:customer_count_by_country",
                "识别为国家维度客户数量统计问题。",
            )

        if (
            "Customer" in table_names
            and self._contains_any(effective_normalized, ("城市",))
            and self._contains_any(effective_normalized, ("客户", "顾客", "用户"))
            and self._contains_any(effective_normalized, ("多少", "数量", "最多", "前", "top"))
        ):
            return (
                "SELECT City, COUNT(*) AS CustomerCount "
                "FROM Customer "
                "WHERE City IS NOT NULL "
                "GROUP BY City "
                f"ORDER BY CustomerCount DESC LIMIT {limit or 5};",
                "rule:customer_count_by_city",
                "识别为城市维度客户数量统计问题。",
            )

        if (
            {"Artist", "Album", "Track"}.issubset(table_names)
            and self._contains_any(effective_normalized, ("艺人", "歌手", "艺术家"))
            and self._contains_any(effective_normalized, ("歌曲", "曲目", "音乐"))
        ):
            return (
                "SELECT ar.Name AS ArtistName, COUNT(t.TrackId) AS TrackCount "
                "FROM Artist ar "
                "JOIN Album al ON ar.ArtistId = al.ArtistId "
                "JOIN Track t ON al.AlbumId = t.AlbumId "
                "GROUP BY ar.ArtistId, ar.Name "
                f"ORDER BY TrackCount DESC LIMIT {limit or 5};",
                "rule:artist_track_count",
                "识别为艺人曲目统计问题，复用 Artist-Album-Track 连接路径。",
            )

        if (
            {"Artist", "Album"}.issubset(table_names)
            and self._contains_any(effective_normalized, ("艺人", "歌手", "艺术家"))
            and self._contains_any(effective_normalized, ("专辑",))
        ):
            return (
                "SELECT ar.Name AS ArtistName, COUNT(al.AlbumId) AS AlbumCount "
                "FROM Artist ar "
                "LEFT JOIN Album al ON ar.ArtistId = al.ArtistId "
                "GROUP BY ar.ArtistId, ar.Name "
                f"ORDER BY AlbumCount DESC LIMIT {limit or 10};",
                "rule:artist_album_count",
                "识别为艺人专辑数量统计问题。",
            )

        if (
            {"Album", "InvoiceLine"}.issubset(table_names)
            and self._contains_any(effective_normalized, ("专辑",))
            and self._contains_any(effective_normalized, ("热门", "最火", "火", "受欢迎", "销量", "购买量"))
        ):
            return (
                "SELECT al.Title AS AlbumTitle, COUNT(il.InvoiceLineId) AS PurchaseCount, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS Revenue "
                "FROM Album al "
                "JOIN Track t ON al.AlbumId = t.AlbumId "
                "JOIN InvoiceLine il ON t.TrackId = il.TrackId "
                "GROUP BY al.AlbumId, al.Title "
                f"ORDER BY PurchaseCount DESC, Revenue DESC LIMIT {limit or 5};",
                "rule:popular_album_by_sales",
                "识别为模糊专辑热度问题，按购买次数和销售额定义热门。",
            )

        if (
            {"MediaType", "Track"}.issubset(table_names)
            and self._contains_any(effective_normalized, ("媒体类型", "格式", "音频格式"))
        ):
            return (
                "SELECT mt.Name AS MediaType, COUNT(t.TrackId) AS TrackCount "
                "FROM MediaType mt "
                "LEFT JOIN Track t ON mt.MediaTypeId = t.MediaTypeId "
                "GROUP BY mt.MediaTypeId, mt.Name "
                "ORDER BY TrackCount DESC;",
                "rule:media_type_count",
                "识别为媒体类型统计问题，生成维度聚合查询。",
            )

        if (
            {"Playlist", "PlaylistTrack"}.issubset(table_names)
            and self._contains_any(effective_normalized, ("播放列表", "歌单"))
        ):
            return (
                "SELECT p.Name AS PlaylistName, COUNT(pt.TrackId) AS TrackCount "
                "FROM Playlist p "
                "LEFT JOIN PlaylistTrack pt ON p.PlaylistId = pt.PlaylistId "
                "GROUP BY p.PlaylistId, p.Name "
                f"ORDER BY TrackCount DESC LIMIT {limit or 5};",
                "rule:playlist_track_count",
                "识别为播放列表歌曲数排行问题，生成多对多统计查询。",
            )

        if (
            "Invoice" in table_names
            and self._contains_any(effective_normalized, ("每年", "年份", "年"))
            and self._contains_any(effective_normalized, ("订单", "发票", "消费"))
        ):
            if year is not None:
                return (
                    "SELECT COUNT(*) AS InvoiceCount "
                    "FROM Invoice "
                    f"WHERE strftime('%Y', InvoiceDate) = '{year}';",
                    "rule:year_filtered_invoice_count",
                    "识别为指定年份订单统计问题。",
                )
            return (
                "SELECT strftime('%Y', InvoiceDate) AS InvoiceYear, COUNT(*) AS InvoiceCount "
                "FROM Invoice "
                "GROUP BY InvoiceYear "
                "ORDER BY InvoiceYear;",
                "rule:yearly_invoice_count",
                "识别为年度订单统计问题，生成时间维度聚合查询。",
            )

        if (
            {"Genre", "Track"}.issubset(table_names)
            and self._contains_any(effective_normalized, ("流派", "风格"))
            and self._contains_any(effective_normalized, ("平均", "avg", "均值"))
            and self._contains_any(effective_normalized, ("时长", "长度", "播放时长"))
        ):
            return (
                "SELECT g.Name AS GenreName, ROUND(AVG(t.Milliseconds) / 1000.0, 2) AS AvgSeconds "
                "FROM Genre g "
                "JOIN Track t ON g.GenreId = t.GenreId "
                "GROUP BY g.GenreId, g.Name "
                f"ORDER BY AvgSeconds DESC LIMIT {limit or 5};",
                "rule:genre_avg_duration",
                "识别为流派平均时长问题，生成 AVG 聚合查询。",
            )

        if (
            {"Genre", "Track"}.issubset(table_names)
            and self._contains_any(effective_normalized, ("流派", "风格"))
            and self._contains_any(effective_normalized, ("歌曲", "曲目", "音乐"))
            and self._contains_any(effective_normalized, ("多少", "数量", "最多", "前", "top"))
        ):
            return (
                "SELECT g.Name AS GenreName, COUNT(t.TrackId) AS TrackCount "
                "FROM Genre g "
                "LEFT JOIN Track t ON g.GenreId = t.GenreId "
                "GROUP BY g.GenreId, g.Name "
                f"ORDER BY TrackCount DESC LIMIT {limit or 5};",
                "rule:genre_track_count",
                "识别为流派歌曲数量统计问题。",
            )

        if (
            {"Employee", "Customer"}.issubset(table_names)
            and self._contains_any(effective_normalized, ("客服", "员工", "销售代表", "支持代表"))
            and self._contains_any(effective_normalized, ("客户", "顾客", "用户"))
        ):
            return (
                "SELECT e.FirstName || ' ' || e.LastName AS SupportRepName, COUNT(c.CustomerId) AS CustomerCount "
                "FROM Employee e "
                "LEFT JOIN Customer c ON e.EmployeeId = c.SupportRepId "
                "GROUP BY e.EmployeeId, SupportRepName "
                f"ORDER BY CustomerCount DESC LIMIT {limit or 5};",
                "rule:support_rep_customer_count",
                "识别为客服负责客户数量统计问题。",
            )

        if (
            "Invoice" in table_names
            and self._contains_any(effective_normalized, ("国家", "地区"))
            and self._contains_any(effective_normalized, ("平均消费", "平均订单金额", "平均销售额", "均值"))
        ):
            return (
                "SELECT BillingCountry, ROUND(AVG(Total), 2) AS AvgOrderValue "
                "FROM Invoice "
                "GROUP BY BillingCountry "
                f"ORDER BY AvgOrderValue DESC LIMIT {limit or 5};",
                "rule:country_average_order_value",
                "识别为国家维度平均消费统计问题。",
            )

        if (
            "Track" in table_names
            and self._contains_any(effective_normalized, ("最长", "最长的", "时长最长"))
            and self._contains_any(effective_normalized, ("歌曲", "曲目", "音乐"))
        ):
            return (
                "SELECT Name, ROUND(Milliseconds / 1000.0, 2) AS Seconds "
                "FROM Track "
                f"ORDER BY Milliseconds DESC, Name ASC LIMIT {limit or 10};",
                "rule:longest_tracks",
                "识别为最长歌曲排行问题。",
            )

        if "Track" in table_names and self._contains_any(effective_normalized, ("单价", "价格", "最贵", "最高价")):
            return (
                "SELECT Name, UnitPrice "
                "FROM Track "
                f"ORDER BY UnitPrice DESC, Name ASC LIMIT {limit or 10};",
                "rule:track_unit_price_ranking",
                "识别为歌曲价格排行问题，生成 Track 排序查询。",
            )

        if (
            "Customer" in table_names
            and self._contains_any(effective_normalized, ("没有公司", "无公司", "公司信息为空", "没有公司信息"))
        ):
            return (
                "SELECT FirstName || ' ' || LastName AS CustomerName, Country "
                "FROM Customer "
                "WHERE Company IS NULL "
                f"ORDER BY CustomerName ASC LIMIT {limit or 10};",
                "rule:customer_without_company",
                "识别为筛选公司信息为空的客户问题。",
            )

        return None, "unsupported", "当前规则未覆盖该问题。"

    def _select_best_example(
        self,
        question: str,
        example_candidates: tuple[ExampleCandidate, ...],
    ) -> ExampleCandidate | None:
        combined_examples = [
            example
            for example in dict.fromkeys((*example_candidates, *self.demo_questions))
            if example.database_id == self.database_id
        ]
        best_example: ExampleCandidate | None = None
        best_score = -1

        for example in combined_examples:
            score = self._score_example(question, example)
            if score > best_score:
                best_score = score
                best_example = example

        return best_example

    def _score_example(self, question: str, example: ExampleCandidate) -> int:
        normalized = question.strip().lower()
        score = 0
        if example.question.strip().lower() == normalized:
            score += 100

        for tag in example.tags:
            if tag and tag.lower() in normalized:
                score += 10

        for keyword in self._extract_keywords(example.question):
            if len(keyword) > 1 and keyword in normalized:
                score += 3

        return score

    def _extract_keywords(self, text: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(token.lower() for token in KEYWORD_PATTERN.findall(text)))

    def _contains_any(self, text: str, terms: tuple[str, ...]) -> bool:
        return any(term in text for term in terms)

    def _extract_limit(self, question: str) -> int | None:
        digit_match = re.search(r"(\d+)", question)
        if digit_match:
            return int(digit_match.group(1))

        chinese_match = re.search(r"([一二两三四五六七八九十]+)", question)
        if not chinese_match:
            return None

        chinese_number = chinese_match.group(1)
        if chinese_number == "十":
            return 10
        if len(chinese_number) == 2 and chinese_number.startswith("十"):
            return 10 + CHINESE_NUMBER_MAP.get(chinese_number[1], 0)
        if len(chinese_number) == 2 and chinese_number.endswith("十"):
            return CHINESE_NUMBER_MAP.get(chinese_number[0], 0) * 10
        if len(chinese_number) == 3 and chinese_number[1] == "十":
            return CHINESE_NUMBER_MAP.get(chinese_number[0], 0) * 10 + CHINESE_NUMBER_MAP.get(chinese_number[2], 0)
        return CHINESE_NUMBER_MAP.get(chinese_number)

    def _extract_year(self, question: str) -> str | None:
        year_match = re.search(r"(19\d{2}|20\d{2})", question)
        if year_match is None:
            return None
        return year_match.group(1)