import sys
from gdascore.gdaTools import setupGdaAttackParameters
from utility.gdaUtility import gdaUtility
import pprint
pp = pprint.PrettyPrinter(indent=4)

gdaUtilityObj=gdaUtility()
paramsList = setupGdaAttackParameters(sys.argv)
print(f" param list:")
pp.pprint(paramsList)
for param in paramsList:
    print("Start next param")
    if param['finished'] == True:
        print("The following Utility measure has been previously completed:")
        pp.pprint(param)
        print(f"Results may be found at {param['resultsPath']}")
        continue
    res = gdaUtilityObj.distinctUidUtilityMeasureSingleAndDoubleColumn(param)
    if res is None:
        print("Unable to complete.")
        pp.pprint(param)
        continue
    print("Finish up")
    gdaUtilityObj.finishGdaUtility(param)
