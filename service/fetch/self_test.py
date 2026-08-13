"""
FAA NOTAM 连通性自测脚本。

用法（从项目根目录运行）:
    python3 service/fetch/self_test.py
或:
    python3 -m service.fetch.self_test

会启动 Camoufox 无头浏览器完成 Akamai 验证（无窗口，跨平台），
依次测试三种查询：按 ICAO、全文搜索、归档。
"""

import os
import sys

# 保证从任意路径运行时都能 import service 包
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from service.fetch.faa_browser import reset_session, get_session


def main():
    session = get_session()
    try:
        print('=' * 55)
        print('开始测试 FAA NOTAM 连通性...')
        print('=' * 55)

        # 测试1: 按 ICAO 查询
        print('\n[测试1] 按 ICAO 查询 (ZBPE)...')
        data = session.search({
            'searchType': '0',
            'designatorsForLocation': 'ZBPE',
            'offset': '0',
            'notamsOnly': 'false'
        })
        n = len(data.get('notamList', []))
        print(f'  ✅ 返回 {n} 条 NOTAM')
        if n == 0:
            print('  ⚠️ 无数据，可能 ZBPE 暂无有效 NOTAM')

        # 测试2: 全文搜索
        print('\n[测试2] 全文搜索 (AEROSPACE)...')
        data2 = session.search({
            'searchType': '4',
            'freeFormText': 'AEROSPACE',
            'offset': '0',
            'notamsOnly': 'false'
        })
        n2 = len(data2.get('notamList', []))
        print(f'  ✅ 返回 {n2} 条 NOTAM')

        # 测试3: 归档查询
        print('\n[测试3] 归档查询 (ZBPE, 2026-07-01)...')
        data3 = session.search({
            'searchType': '5',
            'archiveDate': '2026-07-01',
            'archiveDesignator': 'ZBPE',
            'offset': '0',
            'notamsOnly': 'false'
        })
        n3 = len(data3.get('notamList', []))
        print(f'  ✅ 返回 {n3} 条历史 NOTAM')

        print('\n' + '=' * 55)
        print('✅ 全部测试通过！FAA 数据源可用。')
        print('=' * 55)
        return 0
    except Exception as e:
        print(f'\n❌ 测试失败: {e}')
        return 1
    finally:
        reset_session()


if __name__ == '__main__':
    sys.exit(main())
