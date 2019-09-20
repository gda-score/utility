# Utility

This directory contains tools that measure the utility of anonymization methods.

## To run

To run the tools, you must first install the package `gda-score-code` (see README under `code` repository)

### gdaUtility.py

Contains class `gdaUtility` that executes both coverage and accuracy. 

See https://gda-score.github.io/gdaUtility.m.html for API description.

See https://www.gda-score.org/what-is-a-gda-score/ for a description of how utility is measured.

### accuracyCoverage.py

Routine that reads in the config file (see `accuracyCoverage.py.json`) and executes `gdaUtility()`.
