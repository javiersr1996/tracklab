"""Data quality checks (P3): one function per check over silver, one CSV per check.

Every check writes `reports/quality_<check>.csv` in the long shape of `Result`, one
row per sport, match and metric, so the bulletin reads every check the same way.
"""
