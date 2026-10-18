"""Document-grounded RAG retrieval test-case design.

This module deliberately DOES NOT create network incidents, assert diagnosis labels,
call LLMs, or promote PDF text to device evidence. The source corpus consists of
curated questions with page/heading support references and manually assigned RAG
Gold sections. Those metadata links are not proof that the original PDF was
re-verified at runtime.
"""
from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / 'data' / 'rag_eval' / 'queries_document_grounded.json'
KNOWLEDGE = ROOT / 'knowledge' / 'sanitized'
MAX_CASES = 100


class TestCaseSourceError(ValueError):
    """The curated test-case source is missing, malformed, or ungrounded."""


def _get_rows() -> list[dict]:
    try:
        rows = json.loads(DATASET.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TestCaseSourceError('资料约束 Query 无法读取或不是合法 UTF-8 JSON') from exc
    if not isinstance(rows, list) or len(rows) > 1000:
        raise TestCaseSourceError('资料约束 Query 必须为受限列表')
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise TestCaseSourceError('测试源包含非对象记录')
        cid = row.get('case_id')
        if not isinstance(cid, str) or not re.fullmatch(r'doc_\d{3}', cid) or cid in seen:
            raise TestCaseSourceError('测试源中存在无效或重复的用例标识')
        seen.add(cid)
        source = row.get('source_evidence')
        if not isinstance(source, dict) or not isinstance(source.get('page'), int) or source['page'] < 1:
            raise TestCaseSourceError(f'{cid}: 缺失有效的来源页码')
        for name in ('document', 'heading', 'support', 'interpretation'):
            if not isinstance(source.get(name), str) or not source[name].strip():
                raise TestCaseSourceError(f'{cid}: 缺少来源字段 {name}')
        if '不代表实际发生' not in source['interpretation']:
            raise TestCaseSourceError(f'{cid}: 缺少模拟场景真实性标记')
        if not isinstance(row.get('query'), str) or not row['query'].strip():
            raise TestCaseSourceError(f'{cid}: 缺少 Query')
        if not isinstance(row.get('category'), str):
            raise TestCaseSourceError(f'{cid}: 缺少分类')
        refs = row.get('relevant')
        if not isinstance(refs, list) or not refs:
            raise TestCaseSourceError(f'{cid}: 缺少 RAG Gold')
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get('source'), str):
                raise TestCaseSourceError(f'{cid}: Gold 元数据无效')
            # No arbitrary source file reads. Sources must be curated markdown basenames.
            filename = ref['source']
            if Path(filename).name != filename or not filename.endswith('.md'):
                raise TestCaseSourceError(f'{cid}: Gold 文件路径未列入允许范围')
            path = KNOWLEDGE / filename
            if not path.is_file():
                raise TestCaseSourceError(f'{cid}: 知识库文件不存在: {filename}')
            sections = ref.get('sections')
            if not isinstance(sections, list) or not sections:
                raise TestCaseSourceError(f'{cid}: Gold 缺少章节')
            text = path.read_text(encoding='utf-8')
            # Curated labels refer to a title fragment; the markdown headings are numbered.
            headings = re.findall(r'^#{1,6}\s+(.+?)\s*$', text, re.MULTILINE)
            for section in sections:
                if not isinstance(section, str) or not any(section in heading for heading in headings):
                    raise TestCaseSourceError(f'{cid}: Gold 章节不在知识库标题中: {section}')
    return rows


def list_categories() -> dict:
    rows = _get_rows()
    return {
        'total': len(rows),
        'categories': dict(sorted(Counter(row['category'] for row in rows).items())),
        'source_corpus': 'data/rag_eval/queries_document_grounded.json',
        'provenance_level': 'curated_metadata_not_raw_document_reverification',
        'case_type': 'rag_retrieval_only',
    }


def generate_cases(*, category: str | None = None, limit: int = 34) -> list[dict]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_CASES:
        raise ValueError(f'limit 必须在 1–{MAX_CASES} 之间')
    rows = _get_rows()
    if category:
        if category not in {r['category'] for r in rows}:
            raise ValueError('未知的资料约束分类')
        rows = [r for r in rows if r['category'] == category]
    out = []
    for source in rows[:limit]:
        evidence = source['source_evidence']
        gold = [{'source': r['source'], 'sections': list(r['sections'])} for r in source['relevant']]
        out.append({
            'test_id': 'RAG_' + source['case_id'].upper(),
            'title': '检索核验：' + source['query'],
            'category': source['category'],
            'priority': 'P1',  # Engineering test priority, not a fact asserted by the source.
            'priority_basis': 'engineering_default_not_telecom_source_fact',
            'type': 'rag_retrieval',
            'query': source['query'],
            'preconditions': [
                '使用项目受控脱敏知识库及已建立的向量索引',
                '运行时使用同一知识版本，且 Embedding 服务可用',
            ],
            'steps': [
                '将 Query 提交给 RAG 检索层，设置 Top-K = 3',
                '记录返回知识片段的来源文件、章节与顺序',
                '对照本测试用例的 Gold 来源文件和章节判断是否命中',
            ],
            'expected': [
                '前 3 个检索结果中至少存在一个与 Gold 文件及章节匹配的知识片段；未命中则记为失败，不允许补造结果',
                '仅评价检索命中，不宣称证明实际设备故障或故障分类正确',
            ],
            'gold': gold,
            'provenance': {
                'document': evidence['document'],
                'page': evidence['page'],
                'heading': evidence['heading'],
                'support': evidence['support'],
                'interpretation': evidence['interpretation'],
            },
            'verification_state': 'not_executed',
            'source_verification': 'metadata_linked_requires_original_document_for_reverification',
        })
    return out


def render_cases(cases: list[dict], format: Literal['json', 'markdown', 'csv'] = 'json') -> str:
    if format == 'json':
        return json.dumps(cases, ensure_ascii=False, indent=2) + '\n'
    if format == 'markdown':
        parts = [
            '# 电信资料约束的 RAG 检索测试用例（待执行）',
            '',
            '> 这些是从已标注 Query 生成的测试**设计**，不是实际通过记录、网络故障工单或诊断准确率。',
            '> 来源字段为人工整理的元数据关联，原始电信 PDF 需另行复核；不能据此宣称每条都经过原文独立验证。',
        ]
        for c in cases:
            p = c['provenance']
            parts += [
                '', '## ' + c['test_id'] + ' — ' + c['title'],
                '', '- 类型：RAG 检索测试（非故障分类）',
                '- 优先级：P1（工程默认）',
                '- 当前执行状态：未执行',
                '- 电信资料来源：' + p['document'] + '，第 ' + str(p['page']) + ' 页，' + p['heading'],
                '- 原文支持要点：' + p['support'],
                '- Query：' + c['query'],
                '','### 前置条件',
            ]
            parts += [str(i)+'. '+s for i,s in enumerate(c['preconditions'], 1)]
            parts += ['', '### 测试步骤']
            parts += [str(i)+'. '+s for i,s in enumerate(c['steps'], 1)]
            parts += ['', '### 预期结果']
            parts += [str(i)+'. '+s for i,s in enumerate(c['expected'], 1)]
            parts += ['', '### Gold 相关知识']
            parts += ['- ' + r['source'] + ' / ' + '、'.join(r['sections']) for r in c['gold']]
        return '\n'.join(parts) + '\n'
    if format == 'csv':
        buf = io.StringIO(newline='')
        writer = csv.DictWriter(buf, fieldnames=['test_id','category','priority','query','source_document','page','heading','support','gold','preconditions','steps','expected','verification_state'])
        writer.writeheader()
        for c in cases:
            p = c['provenance']
            writer.writerow({
                'test_id': c['test_id'], 'category': c['category'],
                'priority': c['priority'], 'query': c['query'],
                'source_document': p['document'], 'page': p['page'],
                'heading': p['heading'], 'support': p['support'],
                'gold': '; '.join(r['source']+'::'+'|'.join(r['sections']) for r in c['gold']),
                'preconditions': ' | '.join(c['preconditions']),
                'steps': ' | '.join(c['steps']),
                'expected': ' | '.join(c['expected']),
                'verification_state': c['verification_state'],
            })
        return buf.getvalue()
    raise ValueError('只支持 json / markdown / csv')
