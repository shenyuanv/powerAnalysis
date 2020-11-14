import sys
import sqlite3
from datetime import datetime
from datetime import timedelta
import numpy as np
import argparse
from collections import namedtuple

def contiguous_regions(condition):
    d = np.diff(condition)
    idx, = d.nonzero() 

    idx += 1

    if condition[0]:
        idx = np.r_[0, idx]

    if condition[-1]:
        idx = np.r_[idx, condition.size]

    idx.shape = (-1,2)
    return idx


def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


def extractSecondsActiveFromResultSet(rows, activeState):
	x = [datetime.fromtimestamp(row[0]) for row in rows]
	y = [row[1] for row in rows]
	condition = np.abs(y) == activeState

	regions = contiguous_regions(condition)
	count = timedelta(0)

	for reg in regions:
		timeOfRow = x[reg[0]];
	
		if (reg[1] < len(x)):
			count += (x[reg[1]] - x[reg[0]])
	return count.total_seconds()

def formatTimeDelta(timedelta):
	hours, remainder = divmod(timedelta.total_seconds, 3600)
	minutes, seconds = divmod(remainder, 60) 
	return  '%d:%02d:%02d' % (hours, minutes, seconds)

def main(argv):
	parser=argparse.ArgumentParser()
	parser.add_argument('inputFile')
	parser.add_argument('-s', "--startDate", help="The Start Date - format YYYY-MM-DD HH:MM", required=False, type=valid_date)
	parser.add_argument('-e', "--endDate", help="The End Date - format YYYY-MM-DD HH:MM", required=False, type=valid_date)
	args=parser.parse_args()

	whereClause = ''

	if args.startDate:
		whereClause = 'timestamp > {startDate} '.format(startDate = args.startDate.strftime('%s'))

	if args.endDate:
		if args.startDate:
			whereClause += ' AND '
		whereClause += ' timestamp < {endDate} '.format(endDate = args.endDate.strftime('%s')) 

	db = sqlite3.connect(argv[0])
	db.row_factory = sqlite3.Row
	cursor = db.cursor()

	cursor.execute('''SELECT timestamp, Active 
						FROM PLDisplayAgent_EventPoint_Display {whereClause} 
						ORDER BY timestamp'''.format(whereClause=('', 'WHERE {0}'.format(whereClause))[len(whereClause) > 0]))

	all_rows = cursor.fetchall()
	if len(all_rows):
		displayOnLength =extractSecondsActiveFromResultSet(all_rows, 1)
	else:
		displayOnLength = 0

	cursor.execute('''SELECT  timestamp, state 
						 FROM PLSleepWakeAgent_EventForward_PowerState {whereClause} 
						 ORDER BY timestamp'''.format(whereClause=('', 'WHERE {0}'.format(whereClause))[len(whereClause) > 0]))

	all_rows = cursor.fetchall()
	if len(all_rows):
		deviceOnLength =extractSecondsActiveFromResultSet(all_rows, 0)
	else:
		deviceOnLength = 0

	(startTimeInData, endTimeInData) = (all_rows[0][0], all_rows[-1][0])

	overallBreakdown = '''<table  class="table table-striped table-bordered display responsive">
									<tbody>
										<tr><td>Display active for {0}</td></tr>
										<tr><td>Device active for {1}</td></tr>
									</tbody>
								</table>
						'''.format(str(timedelta(seconds=displayOnLength)),str(timedelta(seconds=deviceOnLength)))

	# App list

	cursor.execute('''SELECT AppName, AppBundleId, AppBundleVersion, AppIs3rdParty
						FROM PLApplicationAgent_EventNone_AllApps''')

	all_rows = cursor.fetchall()
	
	appListBody = ''
	for row in all_rows:
		appListBody += '<tr><td>{0}</td><td>{1}</td><td>{2}</td></tr>\n'.format(row[0], row[1], row[2])
	
	applistBreakdown = '''<table id="applistBreakDown" class="table table-striped table-condensed">
								<thead>
								<tr>
									<td class="col-md-3">App Name</td>
									<td>AppBundleId</td>
									<td>AppBundleVersion</td>
								</tr>
								</thead>
								<tbody>{appListBody}</tbody>
							</table>'''.format(appListBody = appListBody)

	# Per Process Timing

	cursor.execute('''SELECT processname, SUM(value) AS TotalTime 
						FROM PLProcessMonitorAgent_EventInterval_ProcessMonitorInterval_Dynamic, PLProcessMonitorAgent_EventInterval_ProcessMonitorInterval 
						WHERE PLProcessMonitorAgent_EventInterval_ProcessMonitorInterval.ID = PLProcessMonitorAgent_EventInterval_ProcessMonitorInterval_Dynamic.FK_ID
							 {whereClause}
					 	GROUP BY processname 
					 	ORDER BY TotalTime DESC'''.format(whereClause=('', 'AND {0}'.format(whereClause))[len(whereClause) > 0]))

	all_rows = cursor.fetchall()
	
	perProcessBreakdownBody = ''
	for row in all_rows:
		perProcessBreakdownBody += '<tr><td>{0}</td><td>{1}</td></tr>\n'.format(row[0], row[1])
	
	perProcesssBreakdown = '''<table id="processBreakdown" class="table table-striped table-condensed">
								<thead>
								<tr>
									<td class="col-md-3">Process Name</td>
									<td>Time (s)</td>
								</tr>
								</thead>
								<tbody>{perProcessBreakdownBody}</tbody>
							</table>'''.format(perProcessBreakdownBody = perProcessBreakdownBody)


	# Signal Bars
	cursor.execute('''SELECT signalBars, ROUND(CAST(COUNT(*) AS REAL)/total, 2) * 100 AS percent 
				FROM PLBBAgent_EventPoint_TelephonyActivity 
  				CROSS JOIN
				    ( SELECT COUNT(*) AS total 
				      FROM PLBBAgent_EventPoint_TelephonyActivity 
					  WHERE airplaneMode="off" 
					  {whereClause}
				    )
				WHERE airplaneMode="off" {whereClause}
				GROUP BY signalBars'''.format(whereClause=('', 'AND {0}'.format(whereClause))[len(whereClause) > 0]))

	all_rows = cursor.fetchall()

	signalBody = ''
	for row in all_rows:
		signalBody += '<tr><td>{0}</td><td>{1}</td></tr>\n'.format(row[0], row[1])
	
	signalBreakdown = '''<table id="signalBreakdown" class="table table-striped table-condensed">
								<thead>
									<tr>
									<td class="col-md-3">Number of Bars</td>
									<td>%</td>
									</tr>
								</thead>
								<tbody>{signalBody}</tbody>
							</table>'''.format(signalBody = signalBody)


	#locations
	cursor.execute('''SELECT Client, Type, COUNT(Client) AS Count 
						 FROM PLLocationAgent_EventForward_ClientStatus
						 {whereClause}
						 GROUP BY Client ORDER BY Count DESC'''.format(whereClause=('', 'WHERE {0}'.format(whereClause))[len(whereClause) > 0]))

	all_rows = cursor.fetchall()

	locationBody = ''
	for row in all_rows:
		locationBody += '<tr><td>{0}</td><td>{1}</td><td>{2}</td></tr>\n'.format(row[0], row[1], row[2])
	
	locationBreakdown = '''<table id="locationBreakdown" class="table table-striped table-condensed">
								<thead>
									<tr>
									<td class="col-md-3">Client</td>
									<td>Type</td>
									<td>Number of Requests</td>
									</tr>
								</thead>
								<tbody>{locationBody}</tbody>
							</table>'''.format(locationBody = locationBody)

	#power consumption
	cursor.execute('''SELECT Name, SUM(Energy) AS TotalEnergy 
						FROM PLAccountingOperator_Aggregate_RootNodeEnergy, PLAccountingOperator_EventNone_Nodes 
						WHERE PLAccountingOperator_Aggregate_RootNodeEnergy.NodeID = PLAccountingOperator_EventNone_Nodes.ID
							 {whereClause}
					 	GROUP BY Name 
					 	ORDER BY TotalEnergy DESC'''.format(whereClause=('', 'AND {0}'.format(whereClause))[len(whereClause) > 0]))
	all_rows = cursor.fetchall()
	
	perProcessPowerConsumption = ''
	for row in all_rows:
		perProcessPowerConsumption += '<tr><td>{0}</td><td>{1}</td></tr>\n'.format(row[0], row[1])
	
	powerBreakDown = '''<table id="powerBreakDown" class="table table-striped table-condensed">
								<thead>
								<tr>
									<td class="col-md-3">Node Name</td>
									<td>Power Usage</td>
								</tr>
								</thead>
								<tbody>{perProcessPowerConsumption}</tbody>
							</table>'''.format(perProcessPowerConsumption = perProcessPowerConsumption)

	#memory usage
	cursor.execute('''SELECT PLApplicationAgent_EventNone_AllApps.AppName, PLApplicationAgent_EventBackward_ApplicationMemory.AppBundleId, avg(PeakMemory) AS avgpeak 
						FROM PLApplicationAgent_EventBackward_ApplicationMemory 
						LEFT JOIN PLApplicationAgent_EventNone_AllApps 
						ON PLApplicationAgent_EventBackward_ApplicationMemory.AppBundleId = PLApplicationAgent_EventNone_AllApps.AppBundleId 
						{whereClause} 
					 	GROUP BY PLApplicationAgent_EventBackward_ApplicationMemory.AppBundleId 
					 	ORDER BY avgpeak DESC'''.format(whereClause=('', '{0}'.format(whereClause))[len(whereClause) > 0]))
	all_rows = cursor.fetchall()
	
	perProcessMemPeaks = ''
	for row in all_rows:
		AppName = row[0] if row[0] else ''
		perProcessMemPeaks += '<tr><td>{0}</td><td>{1}</td><td>{2}</td></tr>\n'.format(row[1], AppName.encode('utf-8'), row[2])
	
	memoryBreakDown = '''<table id="memoryBreakDown" class="table table-striped table-condensed">
								<thead>
								<tr>
									<td class="col-md-3">AppBundleId</td>
									<td>AppName</td>
									<td>Peak Memory</td>
								</tr>
								</thead>
								<tbody>{perProcessMemPeaks}</tbody>
							</table>'''.format(perProcessMemPeaks = perProcessMemPeaks)


	f = open('report.html', 'w')
	report = '''<html>
		<link rel="stylesheet" type="text/css" href="https://netdna.bootstrapcdn.com/bootstrap/3.0.3/css/bootstrap.min.css">
		<link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/plug-ins/380cb78f450/integration/bootstrap/3/dataTables.bootstrap.css">

		<script type="text/javascript" language="javascript" src="https://code.jquery.com/jquery-1.10.2.min.js"></script>
		<script type="text/javascript" language="javascript" src="https://cdn.datatables.net/1.10.3/js/jquery.dataTables.min.js"></script>
		<script type="text/javascript" language="javascript" src="https://cdn.datatables.net/plug-ins/380cb78f450/integration/bootstrap/3/dataTables.bootstrap.js"></script>

		<script type="text/javascript" charset="utf-8">
			$(document).ready(function() {{
				$('#processBreakdown').DataTable( {{
        			"responsive": true,
        			"order": [[ 1, "desc" ]]
    			}});
				$('#notificationBreakdown').DataTable( {{
        			"responsive": true,
        			"order": [[ 1, "desc" ]]
    			}});
				$('#locationBreakdown').DataTable( {{
        			"responsive": true,
        			"order": [[ 1, "desc" ]]
    			}});
				$('#powerBreakDown').DataTable( {{
        			"responsive": true,
        			"order": [[ 1, "desc" ]]
    			}});
				$('#memoryBreakDown').DataTable( {{
        			"responsive": true,
        			"order": [[ 1, "desc" ]]
    			}});
				$('#applistBreakdown').DataTable( {{
        			"responsive": true,
        			"order": [[ 1, "desc" ]]
    			}});
			}});
		</script>

		<body>
			<div class="container">
			<h1>Energy Report - {startDate} to {endDate}<h1>

			<h2>Overall Metrics</h2>
			{overallBreakdown}

			<h2>App list breakdown</h2>
			{applistBreakdown}

			<h2>Process time breakdown</h2>
			{perProcesssBreakdown}

			<h2>Core Location</h2>
			{locationBreakdown}

			<h2>Signal Breakdown</h2>
			{signalBreakdown}

			<h2>Power Breakdown</h2>
			{powerBreakDown}

			<h2>Memory Breakdown</h2>
			{memoryBreakDown}
			</div>
		<body>
	</html>'''.format(startDate = datetime.fromtimestamp(startTimeInData).strftime("%Y-%m-%d %H:%M"), 
						endDate = datetime.fromtimestamp(endTimeInData).strftime("%Y-%m-%d %H:%M"), 
						overallBreakdown = overallBreakdown,
						perProcesssBreakdown = perProcesssBreakdown,
						signalBreakdown=signalBreakdown,
						locationBreakdown = locationBreakdown,
						powerBreakDown = powerBreakDown,
						memoryBreakDown = memoryBreakDown,
						applistBreakdown = applistBreakdown)
	f.write(report)
	f.close()

	db.close()

if __name__ == "__main__":
   main(sys.argv[1:])
