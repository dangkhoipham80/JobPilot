"""Employers as rows, and the people at them (batch 2 of the intake extension).

Public surface is :mod:`jobpilot.companies.service`. Imported by name rather
than re-exported here, for the reason ``jobpilot.crawler`` documents the hard
way: a package that re-exports both a module and a same-named function turns
``from jobpilot.companies import service`` into a coin flip that fails at
runtime instead of at import.
"""
