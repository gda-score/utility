import copy
import json
import os
import pprint
import random
import sys
from statistics import mean, stdev

from gdascore.gdaQuery import findQueryConditions
from gdascore.gdaAttack import gdaAttack
from gdascore.gdaTools import getDatabaseInfo, makeGroupBy

pp = pprint.PrettyPrinter(indent=4)
# '''
# _Log_File="../log/utility.log"
# 
# def createTimedRotatingLog():
#     logger =logging.getLogger('RotatingLog')
#     logger.setLevel(logging.INFO)
#     formatter = logging.Formatter('%(asctime)s| %(levelname)s| %(message)s','%m/%d/%Y %I:%M:%S %p')
#     handler = TimedRotatingFileHandler(_Log_File,when='midnight',interval=1,backupCount=0)
#     handler.setFormatter(formatter)
#     logger.addHandler(handler)
#     return logger
# 
# logging = createTimedRotatingLog()
# '''
class gdaUtility:
    def __init__(self):
        '''Measures the utility of anonymization methods.

           See `distinctUidUtilityMeasureSingleAndDoubleColumn()` for
           details on how to run. <br/>
           Currently limited to simple count of distinct users.
        '''
        self._ar={}
        self._p = True
        self._nonCoveredDict = dict(accuracy=None,col1="TBD",
                coverage=dict(colCountManyRawDb=None,
                    colCountOneRawDb=None,
                    coveragePerCol=0.0,
                    totalValCntAnonDb=None,
                    valuesInBothRawAndAnonDb=None))
        self._rangeDict = dict(col1="TBD",
                coverage=dict(colCountManyRawDb=None,
                    colCountOneRawDb=None,
                    coveragePerCol="TBD",
                    totalValCntAnonDb=None,
                    valuesInBothRawAndAnonDb=None))

    def _getWorkingColumns(self,tabChar,allowedColumns):
        # I'd like to work with a good mix of data types (numeric, datetime,
        # and text), i.e. targetCols. Also try to get a few with the most
        # distinct values because this gives us more flexibility
        print("getWorkingCOlumns")
        targetCols = 8
        columns = []
        tuples = []
        # Start by putting the desired number of numeric columns in the list
        pp.pprint(tabChar)
        for col in tabChar:
            if (((tabChar[col]['column_type'] == "real") or
                    ((tabChar[col]['column_type'][:3] == "int"))) and
                    (col in allowedColumns)):
                tuples.append([col,tabChar[col]['num_distinct_vals']])
        ordered = sorted(tuples, key=lambda t: t[1], reverse=True)
        for i in range(len(ordered)):
            if i >= targetCols:
                break
            columns.append(ordered[i][0])
        # Then datetime
        tuples = []
        for col in tabChar:
            if (tabChar[col]['column_type'][:4] == "date" and
                    col in allowedColumns):
                tuples.append([col,tabChar[col]['num_distinct_vals']])
        ordered = sorted(tuples, key=lambda t: t[1], reverse=True)
        for i in range(len(ordered)):
            if i >= targetCols:
                break
            columns.append(ordered[i][0])
        # Then text
        tuples = []
        for col in tabChar:
            if (tabChar[col]['column_type'] == "text" and
                    col in allowedColumns):
                tuples.append([col,tabChar[col]['num_distinct_vals']])
        ordered = sorted(tuples, key=lambda t: t[1], reverse=True)
        for i in range(len(ordered)):
            if i >= targetCols:
                break
            columns.append(ordered[i][0])
        return columns

    def _getQueryStats(self,queries,ranges):
        qs = {}
        qs['totalQueries'] = len(queries)
        single = {}
        double = {}
        sizes = {}
        totalSingleColumn = 0
        totalDoubleColumn = 0
        for q in queries:
            if len(q['info']) == 1:
                totalSingleColumn += 1
                col = q['info'][0]['col']
                if col in single:
                    single[col] += 1
                else:
                    single[col] = 1
            else:
                totalDoubleColumn += 1
                key = q['info'][0]['col'] + ':' + q['info'][1]['col']
                if key in double:
                    double[key] += 1
                else:
                    double[key] = 1
            size = q['bucket'][-1]
            if self._p: print(f"bucket {q['bucket']}, size {size}")
            for ran in ranges:
                if size >= ran[0] and size < ran[1]:
                    key = str(f"{ran[0]}-{ran[1]}")
                    if key in sizes:
                        sizes[key] += 1
                    else:
                        sizes[key] = 1
        qs['singleColumn'] = {}
        qs['singleColumn']['totalQueries'] = totalSingleColumn
        qs['singleColumn']['stats'] = single
        qs['doubleColumn'] = {}
        qs['doubleColumn']['totalQueries'] = totalDoubleColumn
        qs['doubleColumn']['stats'] = double
        qs['ranges'] = sizes
        return qs

    def _measureAccuracy(self,param,attack,tabChar,table,uid,allowedColumns):
        ranges = param['basicConfig']['ranges']
        numSamples = param['basicConfig']['samples']
        numColumns = [1,2]
        columns = self._getWorkingColumns(tabChar,allowedColumns)
        for col in columns:
            if col in allowedColumns:
                print(f"Column {col} should not be chosen ({allowedColumns})")
        queries = []
        for rang in ranges:
            for nc in numColumns:
                cond = []
                q = findQueryConditions(param, attack, columns, allowedColumns,
                        rang[0], rang[1], numColumns=nc)
                pp.pprint(q)
                while(1):
                    res = q.getNextWhereClause()
                    if res is None:
                        break
                    cond.append(res)
                # shuffle the query conditions we found and take the first
                # <numSamples> ones
                random.shuffle(cond)
                queries += cond[:numSamples]
                if self._p: pp.pprint(queries)
                if self._p: print(f"Num queries = {len(queries)}")
        # Now go through and make queries for both raw and anon DBs, and
        # record the difference
        anonDb = getDatabaseInfo(param['anonDb'])
        for query in queries:
            if(param['basicConfig']['measureParam']=="rows"):
                sql = str(f"SELECT count(*) FROM {table} ")
            else:
                sql = str(f"SELECT count(DISTINCT {uid}) FROM {table} ")
            sql += query['whereClausePostgres']
            rawAns = self._doExplore(attack,"raw",sql)
            if rawAns is None:
                continue
            if(param['basicConfig']['measureParam']=="rows"):
                sql = str(f"SELECT count(*) FROM {table} ")
            else:
                sql = str(f"SELECT count(DISTINCT {uid}) FROM {table} ")
            if anonDb['type'] == 'aircloak':
                sql += query['whereClauseAircloak']
            else:
                sql += query['whereClausePostgres']
            anonAns = self._doExplore(attack,"anon",sql)
            if anonAns is None:
                continue
            query['raw'] = rawAns[0][0]
            query['anon'] = anonAns[0][0]

        queryStats = self._getQueryStats(queries,ranges)
        accScore = {}
        accScore['queries'] = queryStats
        accScore['accuracy'] = self._calAccuracy(queries,param)
        if self._p: pp.pprint(accScore)
        return accScore

    def _measureCoverage(self,param,attack,tabChar,table,
            rawColNames,anonColNames):
        # Here I only look at individual columns,
        # making the assumption that if I can query an individual column,
        # then I can also query combinations of columns.

        # Each entry in this list is for one column
        coverageScores=[]
        for colName in rawColNames:
            # These hold the query results or indication of lack thereof
            rawDbrowsDict = {}
            anonDbrowsDict = {}
            # There are couple conditions under which the column can be
            # considered not covered at all.
            if colName not in anonColNames:
                # Column doesn't even exist
                entry = copy.deepcopy(self._nonCoveredDict)
                entry['col1'] = colName
                coverageScores.append(entry)
                continue
            else:
                # See how much of the column is NULL
                sql = str(f"SELECT count({colName}) FROM {table}")
                rawAns = self._doExplore(attack,"raw",sql)
                anonAns = self._doExplore(attack,"anon",sql)
                numRawRows = rawAns[0][0]
                numAnonRows = anonAns[0][0]
                if numAnonRows == 0:
                    # Column is completely NULL
                    entry = copy.deepcopy(self._nonCoveredDict)
                    entry['col1'] = colName
                    coverageScores.append(entry)
                    continue

            # Ok, there is an anonymized column. 
            if tabChar[colName]['column_label'] == 'continuous':
                # If a column is continuous, then in any event it can be
                # completely covered with range queries, though only if
                # range queries are possible
                rangePossible = 1
                # TODO: Here we put checks for any anonymization types that
                # don't have range queries. For now there are no such.
                # if (param['anonType'] == 'foobar':
                if rangePossible:
                    entry = copy.deepcopy(self._rangeDict)
                    entry['col1'] = colName
                    entry['coverage']['coveragePerCol'] = numAnonRows/numRawRows
                    coverageScores.append(entry)
                    continue
                else:
                    pass

            # Ok, the anonymized column is not covered by a range (either
            # enumerative or no range function exists), so query the DB to
            # evaluate coverage
            sql = "SELECT "
            sql += (colName)
            if(param['basicConfig']['measureParam']=="rows"):
                sql += str(f", count(*) FROM {table} ")
            else:
                sql += str(f", count( distinct {param['uid']}) FROM {table} ")
            sql += makeGroupBy([colName])

            rawDbrows = self._doExplore(attack,"raw",sql)
            anonDbrows = self._doExplore(attack,"anon",sql)

            for row in anonDbrows:
                anonDbrowsDict[row[0]] = row[1]
            for row in rawDbrows:
                rawDbrowsDict[row[0]] = row[1]
            coverageEntry = self._calCoverage(rawDbrowsDict,
                    anonDbrowsDict,[colName],param)
            coverageScores.append(coverageEntry )
        return coverageScores

    def _getAllowedColumns(self,coverageScores):
        # This removes any columns with a coverage score of 0. Such columns
        # either don't exist, or are all NULL. Either way, we can't measure
        # their accuracy
        allowedColumns = []
        for cov in coverageScores:
            if (cov['coverage']['coveragePerCol'] is None or
                    cov['coverage']['coveragePerCol'] > 0.001):
                # (I'm just a bit wary of true zero comparisons)
                allowedColumns.append(cov['col1'])
        return allowedColumns

    #Method to calculate Utility Measure
    def distinctUidUtilityMeasureSingleAndDoubleColumn(self,param):
        ''' Measures coverage and accuracy.

            `param` is a single data structure from the list of structures
            returned by setupGdaAttackParameters().  The elements
            of param as follows: <br/>
            `name`: The basis for the name of the output json file. Should
            be unique among all measures. <br/>
            `rawDb`: The raw (non-anonymized) database info. <br/>
            `anonDb`: The anonymized database info. <br/>
            `table`: The name of the table in the database. <br/>
            `uid`: The name of the uid column. <br/>
            `measureParam`: The thing that gets measured. Only current value
            is "uid", which indicates that counts of distinct uids should
            be measured. <br/>
            `samples`: States the number of samples over which each utility
            group should be measured. <br/>
            `ranges`: A list of ranges. Each range specifies the lower and
            upper bound on the number of "things" that an answer should
            contain as specified by `measureParam`. <br/>
        '''
        print("Enter distinctUidUtilityMeasureSingleAndDoubleColumn")
        attack = gdaAttack(param)
        table = attack.getAttackTableName()
        uid = attack.getUidColName()
        rawColNames = attack.getColNames(dbType='rawDb')
        anonColNames = attack.getColNames(dbType='anonDb')
        if rawColNames is None or anonColNames is None:
            # This can happen if the anon table doesn't exist
            return None
        # Get table characteristics. This tells us if a given column is
        # enumerative or continuous.
        tabChar = attack.getTableCharacteristics()
        if self._p: pp.pprint(tabChar)
        coverageScores = self._measureCoverage(param,attack,tabChar,table,
                rawColNames,anonColNames)
        allowedColumns = self._getAllowedColumns(coverageScores)
        pp.pprint(coverageScores)
        print("Allowed Columns:")
        pp.pprint(allowedColumns)

        accuracyScores = self._measureAccuracy(param,attack,tabChar,
                table,uid,allowedColumns)
        self._ar['coverage']=coverageScores
        self._ar['accuracy']=accuracyScores
        self._ar['tableStats'] = tabChar
        attackResult = attack.getResults()
        self._ar['operational']=attackResult['operational']
        attack.cleanUp()
        return "Done"

    #Finish utility Measure: Write output to a file.
    def finishGdaUtility(self,params):
        """ Writes the utility scores to the output json file.
        """
        if 'finished' in params:
            del params['finished']
        final = {}
        final.update(self._ar)
        final['params'] = params
        final['finished'] = True
        j = json.dumps(final, sort_keys=True, indent=4)
        resultsPath = params['resultsPath']

        directory=os.path.dirname(resultsPath)
        if not os.path.exists(directory):
            e = str(f"Directory doesn't exists in the {resultsPath} to create a file. Create a directory")
            sys.exit(e)

        try:
            f = open(resultsPath, 'w')
        except:
            e = str(f"Failed to open {resultsPath} for write")
            sys.exit(e)

        f.write(j)
        f.close()
        return final

    def _calCoverage(self,rawDbrowsDict,anonDbrowsDict,colNames,param):
        #logging.info('RawDb Dictionary and AnnonDb Dictionary: %s and %s', rawDbrowsDict, anonDbrowsDict)
        noColumnCountOnerawDb=0
        noColumnCountMorerawDb=0
        valuesInBoth=0
        coverage=dict()
        for rawkey in rawDbrowsDict:
            if rawDbrowsDict[rawkey]==1:
                noColumnCountOnerawDb += 1
            else:
                noColumnCountMorerawDb += 1
        for anonkey in anonDbrowsDict:
            if anonkey in rawDbrowsDict:
                if rawDbrowsDict[anonkey] >1:
                    valuesInBoth += 1
        valuesanonDb=len(anonDbrowsDict)

        #Coverage Metrics
        coverage['coverage'] = {}
        coverage['coverage']['colCountOneRawDb']=noColumnCountOnerawDb
        coverage['coverage']['colCountManyRawDb']=noColumnCountMorerawDb
        coverage['coverage']['valuesInBothRawAndAnonDb']=valuesInBoth
        coverage['coverage']['totalValCntAnonDb']=valuesanonDb
        if(noColumnCountMorerawDb==0):
            coverage['coverage']['coveragePerCol'] =None
        else:
            coverage['coverage']['coveragePerCol']=valuesInBoth/noColumnCountMorerawDb
        columnParam={}
        colPos=1
        for col in colNames:
            columnParam["col"+str(colPos)]=col
            colPos = colPos + 1
        columnParam.update(coverage)
        return columnParam


    #Method to calculate Coverage and Accuracy
    def _calAccuracy(self,queries,param):
        #logging.info('RawDb Dictionary and AnnonDb Dictionary: %s and %s', rawDbrowsDict, anonDbrowsDict)
        accuracy=dict()
        absErrorList=[]
        simpleRelErrorList=[]
        relErrorList=[]
        for q in queries:
            if 'anon' not in q:
                pp.pprint(queries)
                continue
            if q['anon'] == 0:
                continue
            absErrorList.append((abs(q['anon'] - q['raw'])))
            simpleRelErrorList.append((q['raw']/q['anon']))
            relErrorList.append((
                    (abs(q['anon'] - q['raw'])) / (max(q['anon'], q['raw']))))
        absError=0.0
        simpleRelError=0.0
        relError=0.0
        for item in absErrorList:
            absError += item * item
        if len(absErrorList) > 0:
            absError=absError/len(absErrorList);
        for item in simpleRelErrorList:
            simpleRelError+=item*item
        if len(simpleRelErrorList) > 0:
            simpleRelError=simpleRelError/len(simpleRelErrorList);
        for item in relErrorList:
            relError+=item*item
        if len(relErrorList) > 0:
            relError=relError/len(relErrorList);
        accuracy={}
        accuracy['simpleRelErrorMetrics'] = {}
        accuracy['relErrorMetrics'] = {}

        absDict={}
        if len(absErrorList) > 0:
            absDict['min'] = min(absErrorList)
            absDict['max'] = max(absErrorList)
            absDict['avg'] = mean(absErrorList)
        else:
            absDict['min'] = None
            absDict['max'] = None
            absDict['avg'] = None
        if (len(absErrorList)>1):
            absDict['stddev'] = stdev(absErrorList)
        else:
            absDict['stddev'] = None
        absDict['meanSquareError'] = absError

        if (param['basicConfig']['measureParam']) == "rows":
            absDict['compute'] = "(count((*)rawDb)-count((*)anonDb))"
        else:
            absDict['compute']="(count(distinct_rawDb)-count(distinct_anonDb))"
        accuracy['absolErrorMetrics']=absDict

        #SimpleErrorRelDictionary
        simpleRelDict={}
        if len(simpleRelErrorList) > 0:
            simpleRelDict['min'] = min(simpleRelErrorList)
            simpleRelDict['max'] = max(simpleRelErrorList)
            simpleRelDict['avg'] = mean(simpleRelErrorList)
        else:
            simpleRelDict['min'] = None
            simpleRelDict['max'] = None
            simpleRelDict['avg'] = None
        if(len(simpleRelErrorList)>1):
            simpleRelDict['stddev'] = stdev(simpleRelErrorList)
        else:
            simpleRelDict['stddev'] = None
        simpleRelDict['meanSquareError'] = simpleRelError
        if(param['basicConfig']['measureParam'])=="rows":
            simpleRelDict['compute'] = "(count(rawDb(*))/count(anonDb(*)))"
        else:
            simpleRelDict['compute'] = "(count(distinct_rawDb)/count(distinct_anonDb))"
        accuracy['simpleRelErrorMetrics'] = simpleRelDict

        #RelErrorDictionary
        relDict = {}
        if len(relErrorList) > 0:
            relDict['min'] = min(relErrorList)
            relDict['max'] = max(relErrorList)
            relDict['avg'] = mean(relErrorList)
        else:
            relDict['min'] = None
            relDict['max'] = None
            relDict['avg'] = None
        if(len(relErrorList)>1):
            relDict['stddev'] = stdev(relErrorList)
        else:
            relDict['stddev'] = None

        relDict['meanSquareError'] = relError
        if (param['basicConfig']['measureParam']) == "rows":
            relDict[
                'compute'] = "(abs(count((*)rawDb)-count((*)anonDb))/max(count((*)rawDb),count((*)anonDb)))"
        else:
            relDict['compute'] = "(abs(count(distinct_rawDb)-count(distinct_anonDb))/max(count(distinct_rawDb),count(distinct_anonDb)))"
        accuracy['relErrorMetrics'] = relDict

        return accuracy

    def _doExplore(self,attack,db,sql):
        query = dict(db=db, sql=sql)
        if self._p: print(sql)
        print(sql)   
        attack.askExplore(query)
        reply = attack.getExplore()
        if 'answer' not in reply:
            print("ERROR: reply contains no answer")
            pp.pprint(reply)
            return None
        return reply['answer']
