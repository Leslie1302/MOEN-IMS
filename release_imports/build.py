"""Generate community + request bulk-upload files from the five MMU letters.

Column schemas are taken from the running code, not guessed:
  communities (SHEP)          region, district, community, package_number, consultant_name
  communities (streetlights)  region, district, community, constituency, mp_name
  requests                    material, quantity, region, district, community  (+ optional)

Material names are the EXACT strings from prod's InventoryItem table — the
uploader rejects any row whose material it cannot match by name.
"""
from openpyxl import Workbook

def sheet(path, headers, rows):
    wb = Workbook(); ws = wb.active; ws.append(headers)
    for r in rows: ws.append(r)
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(14, len(h) + 4)
    wb.save(path); print(f"  {path}  ({len(rows)} rows)")

# ── 1. UPPER EAST — HT & LV concrete pole accessories ───────────────────────
# (district, community, HT, LV, contractor)
UE = [
 ('Bongo','Boko-Azumbuo',0,100,'E. K. Asare Enterprise'),
 ('Bongo','Apowongo',0,200,'E. K. Asare Enterprise'),
 ('Bongo','Boko-Kumbilgo',0,130,'E. K. Asare Enterprise'),
 ('Binduri','Soogtinga/Buarin',0,100,'Kasn Engineering and Consult Limited'),
 ('Binduri','Bazua NewTown/Biaka',0,150,'Kasn Engineering and Consult Limited'),
 ('Binduri','Boko',0,240,'Elios Engineering Limited'),
 ('Binduri','Dabuugu/Kukparigu',0,100,'Elios Engineering Limited'),
 ('Binduri','Dulnatinga/Agbelgimvoos',0,100,'Elios Engineering Limited'),
 ('Binduri','Noyoko #1/Poisiga/Naboya',0,95,'Elios Engineering Limited'),
 ('Builsa North','Gadema Tajirinsa',0,169,'Jeopa Company Limited'),
 ('Builsa North','Gadema Tampela',0,100,'Jeopa Company Limited'),
 ('Builsa North','Sakpare Suuni',0,50,'Jeopa Company Limited'),
 ('Builsa North','Bapelugu',0,181,'Jeopa Company Limited'),
 ('Builsa North','Buugin',0,100,'Jeopa Company Limited'),
 ('Builsa North','Tengre Yagre',0,200,'Jeopa Company Limited'),
 ('Builsa North','Nandoya Tatahig',0,50,'Jeopa Company Limited'),
 ('Binduri','Atoba-Mognori',40,50,'Tirago Enterprise'),
 ('Binduri','Atoba-Avoase',26,50,'Tirago Enterprise'),
 ('Binduri','Tansia-Bugrin/Zeego/Kolnatinga',7,50,'Tirago Enterprise'),
 ('Binduri','Kaadi-Kudugu',6,50,'Tirago Enterprise'),
 ('Binduri','Agomisin',50,50,'Tirago Enterprise'),
 ('Binduri','Kaadi/Vako',4,50,'Tirago Enterprise'),
 ('Binduri','Kaad/Fataku/Kualivai',18,50,'Tirago Enterprise'),
 ('Binduri','Wabzug',13,50,'Tirago Enterprise'),
 ('Bongo','Awaa Tarongo Ext',22,0,'Kasn And Consult Limited'),
 ('Bongo','Awale Namoo',7,0,'Kasn And Consult Limited'),
 ('Bongo','Sikabiisi Nayari',12,0,'Kasn And Consult Limited'),
 ('Bongo','Sikabiisi Akondone',12,0,'Kasn And Consult Limited'),
 ('Bongo','Sikabiisi Abokobisi',24,0,'Kasn And Consult Limited'),
 ('Bongo','Lung Dangoogo',7,0,'Kasn And Consult Limited'),
 ('Bongo','Ayourpia',18,0,'Kasn And Consult Limited'),
 ('Bongo','Beolembisi',19,0,'Kasn And Consult Limited'),
 ('Bongo','Beo Mooshidaboro',36,0,'Kasn And Consult Limited'),
 ('Builsa North','Chuchuliga-Yiepala',0,50,'Wilwak Enterprise Limited'),
 ('Builsa North','Molinsa',0,70,'Wilwak Enterprise Limited'),
 ('Builsa North','Tampela',0,90,'Wilwak Enterprise Limited'),
 ('Builsa North','Kaasa',0,100,'Wilwak Enterprise Limited'),
 ('Builsa North','Yiekpen No. 1',0,40,'Wilwak Enterprise Limited'),
 ('Builsa North','Yiekpen No. 2',0,60,'Wilwak Enterprise Limited'),
 ('Builsa North','Jangsa',0,50,'Wilwak Enterprise Limited'),
 ('Builsa North','Fiisa',0,30,'Wilwak Enterprise Limited'),
 ('Binduri','Bansi Winaba',0,100,'Payaba Enterprise'),
 ('Binduri','Ziako Tesnatinga/Buarin',0,120,'Payaba Enterprise'),
]
assert sum(r[2] for r in UE) == 321, sum(r[2] for r in UE)
assert sum(r[3] for r in UE) == 3175, sum(r[3] for r in UE)

sheet('01_communities_SHEP_upper_east.xlsx',
      ['region','district','community','package_number','consultant_name'],
      [['Upper East', d, c, '', 'Holy Engineering'] for d, c, _, _, _ in UE])

# LV only. There is no HT concrete pole accessory in prod's InventoryItem list.
sheet('02_requests_SHEP_upper_east_LV.xlsx',
      ['material','quantity','region','district','community','contractor','notes'],
      [['LV Concrete Pole Accessories', lv, 'Upper East', d, c, con,
        'Ref FY-227/255/015 dated 06-08-2026. Completion of HT & LV works.']
       for d, c, ht, lv, con in UE if lv > 0])

# ── 2. SOUTH TONGU — SHEP-4 additional materials ────────────────────────────
ST = ['Dordoekope','Adzikope','Vigbedorkope','Chiefkope/Tetsakpo']
sheet('03_communities_SHEP_south_tongu.xlsx',
      ['region','district','community','package_number','consultant_name'],
      [['Volta','South Tongu', c, 'SHEP-VR-NTD-TECL-09-16','Donab Engineering Limited'] for c in ST])

NOTE_ST = 'Ref FY-227/255/015 dated 05-08-2026. Additional materials, SHEP-4.'
sheet('04_requests_SHEP_south_tongu.xlsx',
      ['material','quantity','region','district','community','contractor','package_number','notes'],
      [['50 sqmm HD AL. Conductor', 2.6,'Volta','South Tongu','Dordoekope',
        'Transpower Engineering and Construction Limited','SHEP-VR-NTD-TECL-09-16',
        NOTE_ST + ' 2.6 km.'],
       ['35 sqmm HD Cu . Conductor', 60,'Volta','South Tongu','Dordoekope',
        'Transpower Engineering and Construction Limited','SHEP-VR-NTD-TECL-09-16',
        NOTE_ST + ' 60 m.'],
       ['33/0.433, 100KVA. 3-ph', 2,'Volta','South Tongu','Dordoekope',
        'Transpower Engineering and Construction Limited','SHEP-VR-NTD-TECL-09-16',
        NOTE_ST + ' Replaces faulty units at Dordoekope JHS and Dordoekope Clinic.'],
       ['33/0.433, 100KVA. 3-ph', 1,'Volta','South Tongu','Adzikope',
        'Transpower Engineering and Construction Limited','SHEP-VR-NTD-TECL-09-16',
        NOTE_ST + ' Replaces faulty unit at Adzikope.']])

# ── 3. GOMOA WEST — 2,000 streetlights to the MP ────────────────────────────
sheet('05_communities_STREETLIGHTS_gomoa_west.xlsx',
      ['region','district','community','constituency','mp_name'],
      [['Central','Gomoa West','Gomoa West','Gomoa West','Richard Gyan Mensah']])

sheet('06_requests_STREETLIGHTS_gomoa_west.xlsx',
      ['material','quantity','region','district','community','notes'],
      [['150 Watts Led C/W (Photocell & Bolts & Nuts)', 2000,'Central','Gomoa West','Gomoa West',
        'Ref FY-227/255/0151 dated 31-07-2026. Consigned to Hon. Richard Gyan-Mensah, MP. '
        'Installation supervised by ECG.']])

print('\nDone.')
