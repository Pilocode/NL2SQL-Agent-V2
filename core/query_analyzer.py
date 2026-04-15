from __future__ import annotations

import re

from core.models import QueryAnalysis


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+")
STOPWORDS = {
    "的",
    "了",
    "和",
    "是",
    "在",
    "按",
    "以及",
    "请",
    "帮我",
    "一下",
    "一下子",
    "一下吧",
    "给我",
    "看看",
}
COMMON_TERMS = (
    "图书",
    "书籍",
    "书名",
    "作者",
    "客户",
    "顾客",
    "用户",
    "订单",
    "发票",
    "消费",
    "销售",
    "流水",
    "销量",
    "销售额",
    "收入",
    "员工",
    "部门",
    "薪资",
    "工资",
    "歌曲",
    "曲目",
    "音乐",
    "艺人",
    "歌手",
    "专辑",
    "流派",
    "播放列表",
    "歌单",
    "国家",
    "城市",
    "客服",
    "数量",
    "均值",
    "平均",
    "最大",
    "最小",
    "最高",
    "最低",
    "前",
    "top",
    "年份",
    "每年",
    "月份",
    "每月",
    "日期",
    "时长",
    "单价",
    "价格",
    "角色",
    "职责",
    "流水",
    "火",
    "最火",
    "热门",
    "最热门",
    "经典",
    "受欢迎",
)
AMBIGUOUS_TERMS = (
    "火",
    "最火",
    "热门",
    "最热门",
    "经典",
    "受欢迎",
    "最好",
    "最差",
)
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


class QueryAnalyzer:
    def __init__(self, semantic_layer: dict | None = None):
        self.semantic_layer = semantic_layer or {}
        self.domain_terms = self._build_domain_terms()
        self.metric_terms = self._build_metric_terms()
        self.entity_terms = self._build_entity_terms()

    def analyze(self, question: str) -> QueryAnalysis:
        normalized = self._normalize(question)
        tokens = tuple(self._tokenize(normalized))
        intent_tags = tuple(self._detect_intents(normalized))
        metric_hints = tuple(self._extract_metric_hints(normalized))
        entity_hints = tuple(self._extract_entity_hints(normalized))
        ambiguous_terms = tuple(self._extract_ambiguous_terms(normalized))
        time_grain = self._extract_time_grain(normalized)
        top_k = self._extract_top_k(normalized)
        is_follow_up = any(marker in normalized for marker in ("再", "这些", "它们", "上面", "刚才", "继续"))
        return QueryAnalysis(
            original_question=question,
            normalized_question=normalized,
            tokens=tokens,
            intent_tags=intent_tags,
            metric_hints=metric_hints,
            entity_hints=entity_hints,
            ambiguous_terms=ambiguous_terms,
            time_grain=time_grain,
            top_k=top_k,
            is_follow_up=is_follow_up,
        )

    def _normalize(self, question: str) -> str:
        return " ".join(question.strip().lower().split())

    def _tokenize(self, text: str) -> list[str]:
        matches: list[tuple[int, str]] = []
        for term in self.domain_terms:
            start = text.find(term)
            if start >= 0:
                matches.append((start, term))

        for match in TOKEN_PATTERN.finditer(text):
            token = match.group(0).strip().lower()
            if not token or token in STOPWORDS:
                continue
            matches.append((match.start(), token))

        matches.sort(key=lambda item: (item[0], -len(item[1])))

        tokens: list[str] = []
        for _, token in matches:
            if token not in tokens and token not in STOPWORDS:
                tokens.append(token)
        return tokens

    def _detect_intents(self, text: str) -> list[str]:
        intent_tags: list[str] = []
        if any(term in text for term in ("插入", "新增", "添加", "录入", "写入")):
            intent_tags.append("insert")
        if any(term in text for term in ("更新", "修改", "改成", "变更")):
            intent_tags.append("update")
        if any(term in text for term in ("删除", "移除", "清空")):
            intent_tags.append("delete")
        if any(term in text for term in ("创建", "新建", "建表", "创建表")):
            intent_tags.append("create")
        if any(term in text for term in ("新增字段", "增加字段", "修改表结构", "alter", "加列", "改表")):
            intent_tags.append("alter")
        if any(term in text for term in ("删除表", "删除字段", "drop")):
            intent_tags.append("drop")
        if any(term in text for term in ("多少", "几个", "数量", "count", "几位", "几首", "几笔")):
            intent_tags.append("count")
        if any(term in text for term in ("最高", "最大", "top", "最多", "前", "排行", "排名", "最低", "最少")):
            intent_tags.append("ranking")
        if any(term in text for term in ("最多", "最少")) and "count" not in intent_tags:
            intent_tags.append("count")
        if any(term in text for term in ("平均", "avg", "均值")):
            intent_tags.append("average")
        if any(term in text for term in ("总", "sum", "总额", "销售额", "消费", "收入", "花费")):
            intent_tags.append("sum")
        if any(term in text for term in ("哪些", "哪个", "列出", "筛选", "where")):
            intent_tags.append("filter")
        if any(term in text for term in ("占比", "比较", "对比", "相比")):
            intent_tags.append("comparison")
        return intent_tags

    def _extract_metric_hints(self, text: str) -> list[str]:
        metric_hints: list[str] = []
        for metric_name in self.metric_terms:
            if metric_name in text and metric_name not in metric_hints:
                metric_hints.append(metric_name)

        for term in ("数量", "订单数量", "客户数量", "歌曲数量", "平均时长", "平均消费", "销售额", "收入"):
            if term in text and term not in metric_hints:
                metric_hints.append(term)
        return metric_hints

    def _extract_entity_hints(self, text: str) -> list[str]:
        entity_hints: list[str] = []
        for term in self.entity_terms:
            if term in text and term not in entity_hints:
                entity_hints.append(term)
        return entity_hints

    def _extract_ambiguous_terms(self, text: str) -> list[str]:
        return [term for term in AMBIGUOUS_TERMS if term in text]

    def _extract_time_grain(self, text: str) -> str | None:
        if any(term in text for term in ("每年", "年份", "年度", "年")):
            return "year"
        if any(term in text for term in ("每月", "月份", "月")):
            return "month"
        if any(term in text for term in ("每天", "日期", "日")):
            return "day"
        return None

    def _extract_top_k(self, text: str) -> int | None:
        digit_match = re.search(r"(?:前|top)?\s*(\d+)", text)
        if digit_match is not None:
            return int(digit_match.group(1))

        chinese_match = re.search(r"(?:前|top)?\s*([一二两三四五六七八九十]+)", text)
        if chinese_match is None:
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

    def _build_domain_terms(self) -> tuple[str, ...]:
        terms = set(COMMON_TERMS)
        for aliases in self.semantic_layer.get("table_aliases", {}).values():
            terms.update(alias.lower() for alias in aliases if alias)
        for aliases in self.semantic_layer.get("column_aliases", {}).values():
            terms.update(alias.lower() for alias in aliases if alias)
        summary_terms = self.semantic_layer.get("summary_terms", {})
        terms.update(summary_terms.get("database", []))
        for values in summary_terms.get("tables", {}).values():
            terms.update(values)
        for values in summary_terms.get("columns", {}).values():
            terms.update(values)
        terms.update(self._extract_summary_terms(self.semantic_layer.get("database_summary", "")))
        for metric in self.semantic_layer.get("metric_templates", []):
            metric_name = metric.get("name", "").lower()
            if metric_name:
                terms.add(metric_name)
        return tuple(sorted(terms, key=len, reverse=True))

    def _build_metric_terms(self) -> tuple[str, ...]:
        terms = {item.get("name", "").lower() for item in self.semantic_layer.get("metric_templates", []) if item.get("name")}
        terms.update(("销售额", "订单数量", "客户数量", "歌曲数量", "平均消费", "平均时长", "收入"))
        return tuple(sorted(terms, key=len, reverse=True))

    def _build_entity_terms(self) -> tuple[str, ...]:
        terms = set()
        for table_name, aliases in self.semantic_layer.get("table_aliases", {}).items():
            terms.add(table_name.lower())
            terms.update(alias.lower() for alias in aliases if alias)
        for column_key, aliases in self.semantic_layer.get("column_aliases", {}).items():
            terms.add(column_key.lower())
            terms.update(alias.lower() for alias in aliases if alias)
        summary_terms = self.semantic_layer.get("summary_terms", {})
        terms.update(summary_terms.get("database", []))
        for values in summary_terms.get("tables", {}).values():
            terms.update(values)
        for values in summary_terms.get("columns", {}).values():
            terms.update(values)
        terms.update(self._extract_summary_terms(self.semantic_layer.get("database_summary", "")))
        return tuple(sorted(terms, key=len, reverse=True))

    def _extract_summary_terms(self, text: str) -> set[str]:
        terms: set[str] = set()
        for match in TOKEN_PATTERN.finditer(str(text or "").lower()):
            token = match.group(0).strip()
            if not token or token in STOPWORDS or len(token) < 2:
                continue
            terms.add(token)
        return terms