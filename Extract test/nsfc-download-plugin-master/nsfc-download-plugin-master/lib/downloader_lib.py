"""
Shared search and download utilities for NSFC report automation.

Provides Vue state extraction, sidebar interaction, project parsing,
task management, and a reusable SearchRunner class.
"""
import csv
import json
import os
import time
import urllib.parse
from datetime import datetime

from .config_loader import NSFC_HOST, MAX_RESULTS_THRESHOLD
from .notify import push

# ── Vue state extraction ──────────────────────────────────────────────────────

def get_vue_data(client):
    """Extract Vue component state (finalSearchList) from the page."""
    result = client.evaluate_js("""
    (() => {
        for (const div of document.querySelectorAll('div')) {
            const vm = div.__vueParentComponent?.proxy
                    || div.__vueParentComponent?.instance?.proxy
                    || div.__vue__
                    || null;
            if (vm && vm.$options && vm.$options.name === 'finalSearchList') {
                return JSON.stringify({
                    dataCount: vm.dataCount, pagesCount: vm.pagesCount,
                    currentPage: vm.currentPage, resultsData: vm.resultsData,
                });
            }
        }
        return '{}';
    })()
    """)
    return json.loads(result.get("result", {}).get("value", "{}"))


def get_sidebar_options(client):
    """Extract sidebar filter options from Vue component."""
    result = client.evaluate_js("""
    (() => {
        for (const div of document.querySelectorAll('div')) {
            const vm = div.__vueParentComponent?.proxy
                    || div.__vueParentComponent?.instance?.proxy
                    || div.__vue__
                    || null;
            if (vm && vm.$options && vm.$options.name === 'finalSearchList') {
                const out = {};
                vm.sidebarList.forEach((item, i) => {
                    const opts = [];
                    for (const opt of item.radioList) {
                        if (typeof opt === 'object' && opt !== null)
                            opts.push({value: opt.code || opt.name, label: opt.name});
                        else
                            opts.push({value: opt, label: opt});
                    }
                    out[i] = {title: item.title, options: opts};
                });
                return JSON.stringify(out);
            }
        }
        return '{}';
    })()
    """)
    return json.loads(result.get("result", {}).get("value", "{}"))


def click_sidebar_option(client, text):
    """Click a sidebar radio label by visible text."""
    js = f"""
    (() => {{
        const labels = document.querySelectorAll('.el-radio__label');
        for (const el of labels) {{
            if (el.textContent.trim() === '{text}') {{ el.click(); return 'ok'; }}
        }}
        return 'not-found';
    }})()
    """
    return client.evaluate_js(js).get("result", {}).get("value")


def goto_page(client, page_num):
    """Navigate to page N via Vue pageNum offset."""
    js = f"""
    (() => {{
        for (const div of document.querySelectorAll('div')) {{
            const vm = div.__vueParentComponent?.proxy
                    || div.__vueParentComponent?.instance?.proxy
                    || div.__vue__
                    || null;
            if (vm && vm.$options && vm.$options.name === 'finalSearchList') {{
                vm.pageNum = {(page_num - 1) * 10};
                vm.getResultsDataList(true);
                return 'done';
            }}
        }}
        return 'no';
    }})()
    """
    return client.evaluate_js(js).get("result", {}).get("value")


def wait_for_data_change(client, old_count, timeout=15):
    """Wait for dataCount to change after a filter click."""
    time.sleep(0.5)
    start = time.time()
    while time.time() - start < timeout:
        s = get_vue_data(client)
        dc = s.get("dataCount", 0)
        results = s.get("resultsData") or []
        if dc >= 0 and dc != old_count and len(results) > 0:
            return s
        if dc == 0 and len(results) == 0:
            time.sleep(0.5)
            s2 = get_vue_data(client)
            if s2.get("dataCount") == 0:
                return s2
            continue
        time.sleep(0.3)
    return get_vue_data(client)


# ── Project parsing ───────────────────────────────────────────────────────────

def parse_projects(results_data, keyword, filter_info):
    """Parse Vue results data into list of project dicts."""
    projects = []
    for item in results_data or []:
        if isinstance(item, list) and len(item) >= 2:
            projects.append({
                "id": item[0],
                "name": item[1],
                "approvalNo": item[2] if len(item) > 2 else "",
                "applicationCode": "",
                "projectType": item[3] if len(item) > 3 else "",
                "personInCharge": "",
                "unit": item[4] if len(item) > 4 else "",
                "fundAmount": "",
                "approvalYear": "",
                "conclusionYear": "",
                "keyword": keyword,
                "filter_info": filter_info,
            })
    return projects


# ── Task list management ──────────────────────────────────────────────────────

TASK_FIELDNAMES = [
    "id", "name", "keyword", "approvalNo", "applicationCode",
    "projectType", "personInCharge", "unit", "fundAmount",
    "approvalYear", "conclusionYear",
    "status", "error", "updated_at", "filter_info",
]

TASK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "task_list.csv")


def load_task_list(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_task_list(tasks, filepath):
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TASK_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for t in tasks:
            row = {k: t.get(k, "") for k in TASK_FIELDNAMES}
            writer.writerow(row)


def merge_tasks(existing, new_projects):
    existing_ids = {t["id"] for t in existing}
    count = 0
    for proj in new_projects:
        if proj["id"] not in existing_ids:
            existing.append({
                "id": proj["id"],
                "name": proj["name"],
                "keyword": proj["keyword"],
                "approvalNo": proj.get("approvalNo", ""),
                "applicationCode": proj.get("applicationCode", ""),
                "projectType": proj.get("projectType", ""),
                "personInCharge": proj.get("personInCharge", ""),
                "unit": proj.get("unit", ""),
                "fundAmount": proj.get("fundAmount", ""),
                "approvalYear": proj.get("approvalYear", ""),
                "conclusionYear": proj.get("conclusionYear", ""),
                "status": "pending",
                "error": "",
                "updated_at": datetime.now().isoformat(),
                "filter_info": proj.get("filter_info", ""),
            })
            existing_ids.add(proj["id"])
            count += 1
    return existing, count


# ── Task enrichment ───────────────────────────────────────────────────────────

# API field name mapping (target → actual API field names)
_FIELD_MAP = {
    "applicationCode": ["code"],
    "personInCharge": ["projectAdmin"],
    "fundAmount": ["supportNum"],
    # approvalYear and conclusionYear are parsed from researchTimeScope below
}


def _extract_year(time_scope, index):
    """Extract year from researchTimeScope like '2021-01-01...至2024-12-31...'.

    index=0 for first date (批准年度), index=-1 for last date (结题年度).
    """
    if not time_scope:
        return ""
    import re
    years = re.findall(r"(\d{4})-\d{2}-\d{2}", str(time_scope))
    if not years:
        return ""
    try:
        return years[index]
    except IndexError:
        return years[0] if years else ""


def enrich_task(session, task):
    """Fetch project detail from API and fill missing metadata fields.

    Calls conclusionProjectInfo API, extracts: applicationCode, personInCharge,
    fundAmount, approvalYear, conclusionYear. No-op if all fields already filled.
    """
    # Check all target fields including the derived year fields
    all_targets = list(_FIELD_MAP.keys()) + ["approvalYear", "conclusionYear"]
    fields_needed = [f for f in all_targets if not task.get(f)]
    if not fields_needed:
        return task  # Already enriched

    import requests, time

    for attempt in range(3):
        try:
            resp = session.post(
                f"{NSFC_HOST}/api/baseQuery/conclusionProjectInfo/{task['id']}",
                timeout=15)
            if resp.status_code == 503:
                time.sleep(5 * (attempt + 1))
                continue
            if resp.status_code != 200 or not resp.text.strip():
                return task
            info = resp.json().get("data", {})
            break
        except Exception:
            time.sleep(3)
    else:
        return task  # All retries failed

    if not info or not isinstance(info, dict):
        return task

    for target, candidates in _FIELD_MAP.items():
        for key in candidates:
            val = info.get(key)
            if val is not None and val != "" and not task.get(target):
                task[target] = str(val)
                break

    # Extract years from researchTimeScope (e.g. "2021-01-01...至2024-12-31...")
    scope = info.get("researchTimeScope", "")
    if scope and not task.get("approvalYear"):
        task["approvalYear"] = _extract_year(scope, 0)
    if scope and not task.get("conclusionYear"):
        task["conclusionYear"] = _extract_year(scope, -1)

    # Update name from API if search result name was truncated
    api_name = info.get("projectName")
    if api_name and len(api_name) > len(task.get("name", "")):
        task["name"] = api_name

    return task


def enrich_tasks(session, tasks, delay=1.0):
    """Enrich a list of tasks with API-sourced metadata fields."""
    import time
    all_fields = list(_FIELD_MAP.keys()) + ["approvalYear", "conclusionYear"]
    enriched = 0
    for i, task in enumerate(tasks):
        before = {f: task.get(f, "") for f in all_fields}
        enrich_task(session, task)
        after = {f: task.get(f, "") for f in all_fields}
        if any(not before.get(f) and after.get(f) for f in all_fields):
            enriched += 1
            if enriched <= 3 or enriched % 20 == 0:
                print(f"  [{i+1}/{len(tasks)}] enriched: {task.get('name', '')[:40]}")
        time.sleep(delay)
    print(f"  Enriched {enriched}/{len(tasks)} tasks")
    return tasks


def load_seen_ids(*filepaths):
    """Load all project IDs from existing task CSVs for deduplication."""
    seen = set()
    for fp in filepaths:
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    seen.add(row["id"])
    return seen


# ── Sort order utilities ──────────────────────────────────────────────────────

def discover_vue_props(client):
    """Dump all Vue component property keys (for diagnosing sort mechanism)."""
    result = client.evaluate_js("""
    (() => {
        for (const div of document.querySelectorAll('div')) {
            const vm = div.__vueParentComponent?.proxy
                    || div.__vueParentComponent?.instance?.proxy
                    || div.__vue__
                    || null;
            if (vm && vm.$options && vm.$options.name === 'finalSearchList') {
                const keys = Object.keys(vm).filter(k =>
                    !k.startsWith('_') && !k.startsWith('$') && typeof vm[k] !== 'function'
                );
                const sample = {};
                for (const k of keys.slice(0, 80)) {
                    const v = vm[k];
                    sample[k] = typeof v === 'object'
                        ? (Array.isArray(v) ? `Array(${v.length})` : 'Object')
                        : String(v).slice(0, 120);
                }
                return JSON.stringify({name: vm.$options.name, keys, sample});
            }
        }
        return '{}';
    })()
    """)
    return json.loads(result.get("result", {}).get("value", "{}"))


def get_sort_options(client):
    """Discover sort options from vm.infoSort. Returns list of {label, value} dicts."""
    result = client.evaluate_js("""
    (() => {
        for (const div of document.querySelectorAll('div')) {
            const vm = div.__vueParentComponent?.proxy
                    || div.__vueParentComponent?.instance?.proxy
                    || div.__vue__
                    || null;
            if (vm && vm.$options && vm.$options.name === 'finalSearchList') {
                if (vm.infoSort && vm.infoSort.length > 0) {
                    return JSON.stringify(vm.infoSort);
                }
            }
        }
        return '[]';
    })()
    """)
    info_sort = json.loads(result.get("result", {}).get("value", "[]"))
    if isinstance(info_sort, list) and len(info_sort) > 0:
        return info_sort

    return [
        {'label': '结题年度', 'value': 'enddate'},
        {'label': '批准年度', 'value': 'approveYear'},
        {'label': '支持经费', 'value': 'budget'},
    ]


# Label-to-field mapping discovered from vm.infoSort
_SORT_FIELD_MAP = {
    '结题年度': 'enddate',
    '批准年度': 'approveYear',
    '支持经费': 'budget',
}


def set_sort_order(client, sort_field, ascending=True):
    """Apply sort via Vue component property mutation.

    sort_field: 'enddate' | 'approveYear' | 'budget'
    ascending: True for ascending, False for descending
    """
    js = f"""
    (() => {{
        for (const div of document.querySelectorAll('div')) {{
            const vm = div.__vueParentComponent?.proxy
                    || div.__vueParentComponent?.instance?.proxy
                    || div.__vue__
                    || null;
            if (vm && vm.$options && vm.$options.name === 'finalSearchList') {{
                vm.order = '{sort_field}';
                vm.sorting = {str(ascending).lower()};
                vm.pageNum = 0;
                vm.currentPage = 1;
                vm.getResultsDataList(true);
                return 'ok';
            }}
        }}
        return 'no-vue';
    }})()
    """
    result = client.evaluate_js(js).get("result", {}).get("value", "")
    if result == 'ok':
        time.sleep(2)
        return True
    print(f"    [WARN] Failed to set sort: {sort_field} asc={ascending}")
    return False


# ── SearchRunner ──────────────────────────────────────────────────────────────

class SearchRunner:
    """Unified multi-dimensional search engine.

    Handles the NSFC site's top-100 result limitation by recursively splitting
    search scope using sidebar filters. Optionally rotates through sort orders
    as the outermost loop to capture different result slices.

    Usage:
        runner = SearchRunner(client, seen_ids, sort_orders=['结题年度', '批准年度'])
        projects = runner.run(keyword, [year_opts, category_opts, discipline_opts])
    """

    def __init__(self, client, seen_ids, max_pages=10, skip_values=None, sort_orders=None):
        self.client = client
        self.seen_ids = seen_ids
        self.max_pages = max_pages
        self.skip_values = skip_values or {"近五年"}
        self.sort_orders = sort_orders or []

    # ── Navigation ──────────────────────────────────────────────────────────

    def navigate_and_wait(self, keyword):
        kw = urllib.parse.quote(keyword)
        self.client.navigate(f"{NSFC_HOST}/finalSearchList?s={kw}")
        self.client.wait_for_load(timeout=15)
        time.sleep(5)
        for _ in range(25):
            if get_vue_data(self.client).get("dataCount", 0) > 0:
                break
            time.sleep(1)
        # Wait for sidebar radioList to populate (loads after data)
        for _ in range(10):
            opts = get_sidebar_options(self.client).get("0", {}).get("options")
            if opts and len(opts) > 0:
                break
            time.sleep(0.5)

    # ── Single search ────────────────────────────────────────────────────────

    def fresh_search(self, keyword, filters, filter_info, full_count=None, retry=True,
                      sort_field=None, ascending=True):
        """Navigate + apply sort + apply filters + paginate + collect new projects."""
        collected = []
        self.navigate_and_wait(keyword)

        # Apply sort after navigation, before reading data
        if sort_field:
            time.sleep(1)
            ok = set_sort_order(self.client, sort_field, ascending)
            if not ok:
                print(f"    [WARN] Sort failed: {sort_field} asc={ascending}")
            time.sleep(2)

        s = get_vue_data(self.client)

        for click_text in filters:
            old = s
            click_sidebar_option(self.client, click_text)
            s = wait_for_data_change(self.client, old.get("dataCount", -1))
            time.sleep(1.0)

        total = s.get("dataCount", 0)
        if total == 0:
            return collected, total

        if retry and full_count and len(filters) > 0 and total >= full_count:
            print(f"        Retry: {filter_info}")
            return self.fresh_search(keyword, filters, filter_info, full_count, retry=False,
                                     sort_field=sort_field, ascending=ascending)

        calc_pages = (total + 9) // 10
        pgs = min(calc_pages, self.max_pages)

        prev_ids = None
        projects = parse_projects(s.get("resultsData"), keyword, filter_info)
        if projects:
            prev_ids = {p["id"] for p in projects}
        for p in projects:
            if p["id"] not in self.seen_ids:
                self.seen_ids.add(p["id"])
                collected.append(p)

        for pg in range(2, pgs + 1):
            time.sleep(1.5)
            goto_page(self.client, pg)
            time.sleep(1.5)
            s = get_vue_data(self.client)
            projects = parse_projects(s.get("resultsData"), keyword, filter_info)

            cur_ids = {p["id"] for p in projects} if projects else set()
            if not projects or cur_ids == prev_ids:
                time.sleep(2)
                s = get_vue_data(self.client)
                projects = parse_projects(s.get("resultsData"), keyword, filter_info)

            for p in projects:
                if p["id"] not in self.seen_ids:
                    self.seen_ids.add(p["id"])
                    collected.append(p)
            if projects:
                prev_ids = {p["id"] for p in projects}

        return collected, total

    # ── Recursive split ─────────────────────────────────────────────────────

    def run(self, keyword, dim_groups):
        """Full search: sort rotation (outer loop) → keyword → filter splitting.

        Each sort field is tried with both ascending and descending to capture
        different top-100 result slices.

        dim_groups: list of option lists, one per split level.
          [year_opts]                    → keyword → year
          [year_opts, category_opts]     → keyword → year → category
          [inst_opts, year_opts, kw_opts] → keyword → institution → year → sub-keyword
        """
        all_new = []
        sort_orders = self.sort_orders if self.sort_orders else []

        if not sort_orders:
            # No sort rotation configured — single basic search
            projects, total = self.fresh_search(keyword, [], f"{keyword}")
            print(f"    {keyword}: {total} results, collected {len(projects)}")
            all_new.extend(projects)
            if total > MAX_RESULTS_THRESHOLD and dim_groups:
                all_new.extend(self._split(keyword, [], dim_groups, total, ""))
        else:
            for field_label in sort_orders:
                sort_field = _SORT_FIELD_MAP.get(field_label)
                if not sort_field:
                    print(f"  [WARN] Unknown sort field '{field_label}', skipping")
                    continue
                for ascending in (True, False):
                    direction = "↑" if ascending else "↓"
                    sort_tag = f"{field_label}{direction}"
                    print(f"  [Sort: {sort_tag}] {keyword}")

                    projects, total = self.fresh_search(
                        keyword, [], f"{keyword} (sort={sort_tag})",
                        sort_field=sort_field, ascending=ascending
                    )
                    print(f"    {keyword} (sort={sort_tag}): {total} results, collected {len(projects)}")
                    all_new.extend(projects)

                    if total == 0:
                        continue

                    if total > MAX_RESULTS_THRESHOLD and dim_groups:
                        all_new.extend(self._split(keyword, [], dim_groups, total, "",
                                                   sort_field, ascending))

        if all_new:
            push("搜索完成", f"关键词「{keyword}」找到 {len(all_new)} 个新项目")
        return all_new

    def _split(self, keyword, parent_filters, dim_groups, full_count, prefix,
               sort_field=None, ascending=True):
        """Recursively split by dimensions, collecting results at each leaf."""
        if not dim_groups:
            return []

        all_new = []
        options = dim_groups[0]
        usable = [o for o in options
                  if o.get('label', o.get('value', '')) not in self.skip_values]

        for opt in usable:
            label = opt.get("label", opt.get("value", ""))
            filters = parent_filters + [label]
            new_prefix = f"{prefix}/{label}" if prefix else label
            proj, cnt = self.fresh_search(keyword, filters, f"{keyword}/{new_prefix}",
                                          full_count, sort_field=sort_field, ascending=ascending)
            if proj:
                print(f"    {new_prefix}: {cnt} results, collected {len(proj)}")
            all_new.extend(proj)
            time.sleep(0.3)

            if 0 < cnt < full_count and cnt > MAX_RESULTS_THRESHOLD and len(dim_groups) > 1:
                deeper = self._split(keyword, filters, dim_groups[1:], full_count,
                                     new_prefix, sort_field, ascending)
                all_new.extend(deeper)

        return all_new
