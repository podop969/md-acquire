# NSFC Search Strategies

## The 100-Result Limit Problem

The NSFC search endpoint (`kd.nsfc.cn/finalSearchList`) only returns the top 100 results
for any query. For broad keywords (e.g., "battery" with 900+ results), a single query
will miss 800+ projects.

## Solution: Multi-Dimensional Splitting

The tool uses sidebar filters to progressively narrow search scope:

### Dimension 1: Year (年度)
Filter by approval year. Each year typically contains a subset of total results.

### Dimension 2: Funding Category (资助类别)
Further split by funding type (面上项目, 青年科学基金项目, etc.).

### Dimension 3: Discipline (学科)
Fine-grained split by research discipline (e.g., 化学科学, 工程与材料科学).

### Dimension 4: Institution (依托单位)
Split by the host institution of the project.

## Splitting Algorithm

```
For each keyword:
  1. Search with no filter → get total_count
  2. If total_count > 90 (threshold):
     For each year:
       Search with year filter → get year_count
       If year_count > 90:
         For each category:
           Search with year + category → get cat_count
           If cat_count > 90:
             For each discipline:
               Search with year + category + discipline
```

## When to Use Each Script

| Script | Splitting Strategy | Best For |
|--------|-------------------|----------|
| `search-keyword.py` | keyword → year → category → discipline | Main keywords with many results |
| `search-sub-keywords.py` | sub-keyword → year → category | Specific terms with moderate results |
| `search-institution.py` | institution → year → keyword | Finding projects by host university |
| `search-material.py` | keyword → year → category | Material/component terms |
| `search-cold.py` | keyword → year only | Niche terms, usually < 100 results |
| `search-rerun.py` | same as sub-keywords | Retry after Chrome restart |

## Special Values

The sidebar has some non-data values that should be skipped:
- `近五年` (last 5 years) — not a specific year, meaning changes over time
- Any value that provides no useful filter narrowing

These are excluded by `SKIP_VALUES = {"近五年"}` in the search scripts.
