from __future__ import annotations

import re

from core.models import ColumnProfile, ExampleCandidate, QueryAnalysis, RetrievalHit, SQLDraft, SemanticInterpretation


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
        normalized = analysis.normalized_question
        rewritten_question = semantic_interpretation.rewritten_question.lower() if semantic_interpretation is not None else ""
        effective_normalized = rewritten_question or normalized
        table_names = {hit.table_name for hit in retrievals}
        limit = analysis.top_k or self._extract_limit(question)
        year = self._extract_year(question)

        generic_sql, generic_source, generic_rationale = self._generate_generic_rules(
            question,
            analysis,
            retrievals,
            effective_normalized,
            limit,
        )
        if generic_sql is not None:
            return generic_sql, generic_source, generic_rationale

        if self.database_id != "chinook":
            return None, "unsupported", "当前数据库未命中通用 schema 规则，等待 LLM 或 example RAG 生成。"

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

    def _generate_generic_rules(
        self,
        question: str,
        analysis: QueryAnalysis,
        retrievals: tuple[RetrievalHit, ...],
        normalized_question: str,
        limit: int | None,
    ) -> tuple[str | None, str, str]:
        create_sql = self._build_generic_create_table_sql(question, analysis)
        if create_sql is not None:
            return create_sql, "generic:create_table", "识别到建表需求，按问题中的英文表名和字段定义生成 CREATE TABLE。"

        add_column_sql = self._build_generic_add_column_sql(question, analysis, retrievals)
        if add_column_sql is not None:
            return add_column_sql, "generic:add_column", "识别到加列需求，按问题中的英文表名和字段定义生成 ALTER TABLE ADD COLUMN。"

        if not retrievals:
            return None, "unsupported", "当前没有召回到可用于通用生成的 schema。"

        primary_hit = retrievals[0]
        table_name = primary_hit.table_name
        available_columns = tuple(primary_hit.columns)
        selected_columns = self._pick_display_columns(available_columns)
        select_clause = ", ".join(column.name for column in selected_columns) or "*"

        insert_sql = self._build_generic_insert_sql(question, analysis, primary_hit)
        if insert_sql is not None:
            return insert_sql, "generic:insert_row", f"识别到新增数据需求，按表 {table_name} 的显式字段赋值生成 INSERT。"

        update_sql = self._build_generic_update_sql(question, analysis, primary_hit)
        if update_sql is not None:
            return update_sql, "generic:update_row", f"识别到更新数据需求，按表 {table_name} 的显式字段赋值生成 UPDATE。"

        if any(tag == "count" for tag in analysis.intent_tags) or self._contains_any(normalized_question, ("多少", "几条", "数量", "总数", "记录数")):
            return (
                f"SELECT COUNT(*) AS RecordCount FROM {table_name};",
                "generic:count_rows",
                f"识别为通用数量统计问题，按召回最高的表 {table_name} 生成 COUNT 查询。",
            )

        if any(tag == "ranking" for tag in analysis.intent_tags):
            sortable_column = self._pick_sortable_column(available_columns)
            if sortable_column is not None:
                return (
                    f"SELECT {select_clause} FROM {table_name} ORDER BY {sortable_column.name} DESC LIMIT {limit or 10};",
                    "generic:top_rows",
                    f"识别为通用排序问题，按表 {table_name} 中的字段 {sortable_column.name} 生成排行查询。",
                )

        if self._contains_any(normalized_question, ("哪些", "列出", "查看", "查询", "显示", "所有")) or not analysis.intent_tags:
            return (
                f"SELECT {select_clause} FROM {table_name} LIMIT {limit or 20};",
                "generic:list_rows",
                f"未命中特定业务规则，按召回最高的表 {table_name} 生成通用列表查询。",
            )

        return None, "unsupported", "当前问题未命中通用 schema 规则。"

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

    def _pick_display_columns(self, columns: tuple[ColumnProfile, ...]) -> tuple[ColumnProfile, ...]:
        if not columns:
            return ()
        preferred_columns = [
            column
            for column in columns
            if column.is_primary_key or self._contains_any(column.name.lower(), ("name", "title", "id", "no"))
        ]
        if preferred_columns:
            return tuple(preferred_columns[:4])
        return columns[:4]

    def _pick_sortable_column(self, columns: tuple[ColumnProfile, ...]) -> ColumnProfile | None:
        numeric_columns = [
            column
            for column in columns
            if any(token in column.data_type.lower() for token in ("int", "real", "float", "double", "numeric", "decimal"))
        ]
        if numeric_columns:
            return numeric_columns[0]

        identifier_columns = [
            column
            for column in columns
            if column.is_primary_key or self._contains_any(column.name.lower(), ("id", "no", "date", "time"))
        ]
        if identifier_columns:
            return identifier_columns[0]
        return columns[0] if columns else None

    def _build_generic_insert_sql(self, question: str, analysis: QueryAnalysis, hit: RetrievalHit) -> str | None:
        if "insert" not in analysis.intent_tags:
            return None

        assignments = self._extract_column_assignments(question, tuple(hit.columns))
        if not assignments:
            return None

        column_names = []
        values = []
        for column in hit.columns:
            if column.name not in assignments:
                continue
            column_names.append(column.name)
            values.append(self._format_sql_literal(assignments[column.name], column))

        if not column_names:
            return None
        columns_clause = ", ".join(column_names)
        values_clause = ", ".join(values)
        return f"INSERT INTO {hit.table_name} ({columns_clause}) VALUES ({values_clause});"

    def _build_generic_update_sql(self, question: str, analysis: QueryAnalysis, hit: RetrievalHit) -> str | None:
        if "update" not in analysis.intent_tags:
            return None

        set_assignments = self._extract_column_assignments(question, tuple(hit.columns), require_update_marker=True)
        if not set_assignments:
            return None

        where_column = self._pick_where_column(hit.columns)
        if where_column is None:
            return None
        where_value = self._extract_where_value(question, where_column)
        if where_value is None:
            return None

        set_clauses = []
        for column in hit.columns:
            if column.name == where_column.name or column.name not in set_assignments:
                continue
            set_clauses.append(f"{column.name} = {self._format_sql_literal(set_assignments[column.name], column)}")

        if not set_clauses:
            return None
        where_clause = f"{where_column.name} = {self._format_sql_literal(where_value, where_column)}"
        return f"UPDATE {hit.table_name} SET {', '.join(set_clauses)} WHERE {where_clause};"

    def _build_generic_create_table_sql(self, question: str, analysis: QueryAnalysis) -> str | None:
        if "create" not in analysis.intent_tags and not re.search(r"create\s+table", question, flags=re.IGNORECASE):
            return None

        table_name = self._extract_target_table_name(question, create_only=True)
        if not table_name:
            return None

        columns = self._extract_column_definitions(question)
        if not columns:
            return None

        column_sql = []
        for index, (column_name, data_type) in enumerate(columns):
            suffix = " PRIMARY KEY" if index == 0 and column_name.lower().endswith("id") else ""
            column_sql.append(f"{column_name} {data_type}{suffix}")
        return f"CREATE TABLE {table_name} ({', '.join(column_sql)});"

    def _build_generic_add_column_sql(
        self,
        question: str,
        analysis: QueryAnalysis,
        retrievals: tuple[RetrievalHit, ...],
    ) -> str | None:
        if "alter" not in analysis.intent_tags and not re.search(r"add\s+column", question, flags=re.IGNORECASE):
            return None

        table_name = self._extract_target_table_name(question)
        if not table_name and retrievals:
            table_name = retrievals[0].table_name
        if not table_name:
            return None

        column_definitions = self._extract_column_definitions(question)
        if not column_definitions:
            add_column_match = re.search(
                r"(?:新增字段|增加字段|新增列|加列|add\s+column)\s+([A-Za-z_][A-Za-z0-9_]*)\s+(INTEGER|TEXT|REAL|BLOB|NUMERIC|DATETIME|DATE|FLOAT|DOUBLE|VARCHAR(?:\(\d+\))?)",
                question,
                flags=re.IGNORECASE,
            )
            if add_column_match is None:
                return None
            column_definitions = [(add_column_match.group(1), add_column_match.group(2).upper())]

        column_name, data_type = column_definitions[0]
        return f"ALTER TABLE {table_name} ADD COLUMN {column_name} {data_type};"

    def _extract_target_table_name(self, question: str, create_only: bool = False) -> str | None:
        patterns = [
            r"(?:create\s+table|创建(?:一张)?表|新建(?:一张)?表)\s+([A-Za-z_][A-Za-z0-9_]*)",
        ]
        if not create_only:
            patterns.extend(
                [
                    r"([A-Za-z_][A-Za-z0-9_]*)\s*表",
                    r"table\s+([A-Za-z_][A-Za-z0-9_]*)",
                ]
            )

        for pattern in patterns:
            match = re.search(pattern, question, flags=re.IGNORECASE)
            if match is not None:
                return match.group(1)
        return None

    def _extract_column_definitions(self, question: str) -> list[tuple[str, str]]:
        matches = re.findall(
            r"([A-Za-z_][A-Za-z0-9_]*)\s+(INTEGER|TEXT|REAL|BLOB|NUMERIC|DATETIME|DATE|FLOAT|DOUBLE|VARCHAR(?:\(\d+\))?)",
            question,
            flags=re.IGNORECASE,
        )
        columns: list[tuple[str, str]] = []
        for column_name, data_type in matches:
            if column_name.lower() in {"table", "create", "column", "add"}:
                continue
            columns.append((column_name, data_type.upper()))
        return columns

    def _extract_column_assignments(
        self,
        question: str,
        columns: tuple[ColumnProfile, ...],
        require_update_marker: bool = False,
    ) -> dict[str, str]:
        assignments: dict[str, str] = {}
        for segment in re.split(r"[，,；;。]\s*", question):
            normalized_segment = segment.strip()
            if not normalized_segment:
                continue
            for column in columns:
                if not self._segment_mentions_column(normalized_segment, column.name):
                    continue
                if require_update_marker and not re.search(r"(?:改成|改为|更新为|设为|修改为|=|:=)", normalized_segment, flags=re.IGNORECASE):
                    continue
                value = self._extract_assignment_value(normalized_segment, column.name)
                if value is not None:
                    assignments[column.name] = value
        return assignments

    def _extract_assignment_value(self, segment: str, column_name: str) -> str | None:
        patterns = [
            rf"{re.escape(column_name)}\s*(?:=|:=|为|是|:|：|改成|改为|更新为|设为|修改为)\s*('?[^'，,；;。]+'?|\"?[^\"，,；;。]+\"?)",
            rf"{re.escape(column_name)}\s+('?[^'，,；;。]+'?|\"?[^\"，,；;。]+\"?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, segment, flags=re.IGNORECASE)
            if match is None:
                continue
            return match.group(1).strip().strip('"').strip("'")
        return None

    def _pick_where_column(self, columns: tuple[ColumnProfile, ...]) -> ColumnProfile | None:
        for column in columns:
            if column.is_primary_key:
                return column
        return columns[0] if columns else None

    def _extract_where_value(self, question: str, column: ColumnProfile) -> str | None:
        patterns = [
            rf"(?:其中|where|当|把).*?{re.escape(column.name)}\s*(?:=|为|是|:|：)\s*('?[^'，,；;。]+'?|\"?[^\"，,；;。]+\"?)",
            rf"{re.escape(column.name)}\s*(?:=|为|是|:|：)\s*('?[^'，,；;。]+'?|\"?[^\"，,；;。]+\"?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, question, flags=re.IGNORECASE)
            if match is None:
                continue
            return match.group(1).strip().strip('"').strip("'")
        return None

    def _segment_mentions_column(self, segment: str, column_name: str) -> bool:
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(column_name)}(?![A-Za-z0-9_])"
        return re.search(pattern, segment, flags=re.IGNORECASE) is not None

    def _format_sql_literal(self, value: str, column: ColumnProfile) -> str:
        cleaned = value.strip()
        if cleaned.lower() in {"null", "none"}:
            return "NULL"
        if self._is_numeric_value(cleaned) and any(token in column.data_type.lower() for token in ("int", "real", "float", "double", "numeric", "decimal")):
            return cleaned
        escaped = cleaned.replace("'", "''")
        return f"'{escaped}'"

    def _is_numeric_value(self, value: str) -> bool:
        return re.fullmatch(r"-?\d+(?:\.\d+)?", value) is not None

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