import csv, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
src=sys.argv[1]; dst=sys.argv[2]; title=sys.argv[3]
rows=list(csv.reader(open(src)))
wb=Workbook(); ws=wb.active; ws.title='Route'
hdr=['Leg','Day','Depart','Arrive','Board at','Alight at','Carrier','Route','mi','Est hrs','Cum hrs','States on leg','New states','States so far','Price','Cum $','Notes']
ws.append(hdr)
for c in ws[1]: c.font=Font(bold=True,color='FFFFFF'); c.fill=PatternFill('solid',fgColor='1F4E78')
n=0
for r in rows[1:]:
    n+=1; i=n+1
    leg,day,dep,arr,board,alight,car,route,km,mi,hrs,sts,fresh,price,notes=r
    ws.append([int(leg),'','','',board,alight,car,route,int(mi),float(hrs),f'=SUM($J$2:J{i})',sts,fresh,f'=IF(M{i}="",N{i-1},IF(N{i-1}="",M{i},N{i-1}&","&M{i}))' if i>2 else f'=M{i}','',f'=SUM($O$2:O{i})',notes])
    if fresh:
        for c in ws[i]: c.fill=PatternFill('solid',fgColor='E2EFDA')
ws.append([]); ws.append(['Totals','','','','','','','',f'=SUM(I2:I{n+1})',f'=SUM(J2:J{n+1})','','','',f'=LEN(N{n+1})-LEN(SUBSTITUTE(N{n+1},",",""))+1',f'=SUM(O2:O{n+1})'])
ws.cell(n+3,1).font=Font(bold=True)
widths=[5,8,8,8,34,34,20,42,6,7,7,18,10,60,8,8,30]
for i,w in enumerate(widths,1): ws.column_dimensions[get_column_letter(i)].width=w
ws.freeze_panes='A2'
ws2=wb.create_sheet('How to use')
for t in [title,'','Legs come from the shortest-path model on the NTAD Intercity Bus Atlas shapes, assuming perfect connections.',
 'Fill Day / Depart / Arrive / Price from real timetables. Est hrs = distance at ~55 mph intercity (15 mph local).',
 'Green rows are where a new state is first entered. "States so far" and the totals row are formulas.',
 'To test a variation, delete/reorder rows; the formulas recompute. Local bus legs are prefixed LOCAL in the Carrier column.']:
    ws2.append([t])
ws2.column_dimensions['A'].width=110
wb.save(dst); print('saved',dst)
