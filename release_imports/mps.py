from openpyxl import Workbook
# (region, constituency, name, streetlight_qty) — verbatim from Appendix I.
D="""Ahafo|Asunafo North|Mohammed Haruna|200
Ahafo|Asunafo South|Eric Opoku|200
Ahafo|Asutifi North|Ebenezer Kwaku Addo|200
Ahafo|Asutifi South|Collins Dauda|200
Ahafo|Tano North|Gideon Baako|200
Ahafo|Tano South|Charles Asiedu|200
Ashanti|Adansi-Akrofuom|Joseph Azumah|200
Ashanti|Adansi-Asokwa|Godwin Animli Azogbazi-Dorani|200
Ashanti|Afigya Kwabre North|Collins Adomako-Mensah|200
Ashanti|Afigya Kwabre South|Damata Ama Appianimaa Salam|200
Ashanti|Afigya Sekyere East|Mavis Nkansah Boadu|200
Ashanti|Ahafo Ano North|Eric Nana Agyemang Prempeh|200
Ashanti|Ahafo Ano South East|Yakubu Mohammed|200
Ashanti|Ahafo Ano South West|Osei Mensah Dapaah Elvis|200
Ashanti|Asante-Akim Central|Kwame Anyimadu - Antwi|200
Ashanti|Asante-Akim North|Ohene Anyimadu Frimpong|200
Ashanti|Asante-Akim South|Kwaku Asante-Boateng|200
Ashanti|Asawase|Mubarak Mohammed Muntaka|200
Ashanti|Asokwa|Patricia Appiagyei|300
Ashanti|Atwima-Kwanwoma|Kofi Amankwa-Manu|200
Ashanti|Atwima-Mponua|Seth Osei-Akoto|200
Ashanti|Atwima-Nwabiagya North|Frank Yeboah|200
Ashanti|Atwima-Nwabiagya South|Shirley Kyei|200
Ashanti|Bantama|Francis Asenso -Boakye|200
Ashanti|Bekwai|Ralph Poku-Adusei|200
Ashanti|Bosome-Freho|Nana Asado-Adjei|200
Ashanti|Bosomtwe|Yaw Osei Adutwum|200
Ashanti|Effiduase-Asokore|Nana Ayew Afriyie|200
Ashanti|Ejisu|Kwabena Boateng|200
Ashanti|Ejura-Sekyedumase|Muhammad Bawah Braimah|200
Ashanti|Fomena (Adansi North)|Andrew Asiamah Amoako|300
Ashanti|Juaben|Francis Kwabena B. Owusu-Akyaw|200
Ashanti|Kumawu|Ernest Yaw Anim|200
Ashanti|Kwabre East|Onyina-Acheampong Akwasi Gyamfi|200
Ashanti|Kwadaso|Kingsley Nyarko|200
Ashanti|Mampong|Kwaku Ampratwum-Sarpong|200
Ashanti|Manhyia North|Akwasi Konadu|200
Ashanti|Manhyia South|Nana Agyei Baffour Awuah|200
Ashanti|Manso Edubia|Frimpong Yaw Addo|200
Ashanti|Manso Nkwanta|Tweneboa Kodua Fokuo|200
Ashanti|New Edubease|Adams Abdul Salam|200
Ashanti|Nhyiaeso|Stephen Amoah|200
Ashanti|Nsuta-Kwamang-Beposo|Adelaide Ntim|200
Ashanti|Obuasi East|Patrick Boakye Yiadom|200
Ashanti|Obuasi West|Kwaku Agyemang Kwarteng|200
Ashanti|Odotobri|Anthony Mmieh|200
Ashanti|Offinso North|Fred Kyei Asamoah|200
Ashanti|Offinso South|Isaac Yaw Opoku|200
Ashanti|Oforikrom|Michael Kwasi Aidoo|200
Ashanti|Old Tafo|Vincent Ekow Assafuah|200
Ashanti|Sekyere Afram Plains|Nasira Afrah Gyekye|200
Ashanti|Suame|John Darko|200
Ashanti|Subin|Kofi Obiri Yeboah|200
Bono|Banda Ahenkro|Ahmed Ibrahim|200
Bono|Berekum East|Simon Ampaabeng Kyeremeh|200
Bono|Berekum West|Dickson Kyere-Duah|200
Bono|Dormaa Central|John Kwame Adu Jack|200
Bono|Dormaa East|Rachel Amma Owusuah|200
Bono|Dormaa West|Vincent Oppong Asamoah|200
Bono|Jaman North|Frederick Yaw Ahenkwah|200
Bono|Jaman South|Kwadwo Damoah|200
Bono|Sunyani East|Seid Mubarak|200
Bono|Sunyani West|Millicent Yeboah Amankwah|200
Bono|Tain|Adama Sulemana|200
Bono|Wenchi|Haruna Seidu|200
Bono East|Atebubu-Amantin|Sanja Nanja|200
Bono East|Kintampo North|Joseph Kwame Kumah|200
Bono East|Kintampo South|Felicia Adjei|200
Bono East|Nkoranza North|Joseph Kwasi Mensah|200
Bono East|Nkoranza South|Emmanuel Kwadwo Agyekum|200
Bono East|Pru East|Emmanuel Kwaku Boam|200
Bono East|Pru West|Emmanuel Kofi Ntekuni|200
Bono East|Sene East|Dominic Napare|200
Bono East|Sene West|Kwame Twumasi Ampofo|200
Bono East|Techiman North|Elizabeth Ofosu-Adjare|200
Bono East|Techiman South|Martin Adjei-Mensah Korsah|200
Central|Abura-Asebu-Kwamankese|Felix Kwakye Ofosu|200
Central|Agona East|Queenstar Pokua Sawyerr|200
Central|Agona West|Ernestina Ofori Dangbey|200
Central|Ajumako-Enyan-Essiam|Cassiel Ato Baah Forson|200
Central|Asikuma-Odoben-Brakwa|Alhassan Kobina Ghansah|200
Central|Assin Central|Nurien Shaibu Migyimah|200
Central|Assin North|James Gyakye Quayson|200
Central|Assin South|John Ntim Fordjuor|200
Central|Awutu-Senya East|Phillis Naa Koryoo Okunor|200
Central|Awutu-Senya West|Gizella Tetteh Agbotui|200
Central|Cape Coast North|Kwamena Minta Nyarku|200
Central|Cape Coast South|Kweku George Ricketts-Hagan|300
Central|Effutu|Alexander Afenyo-Markin|300
Central|Ekumfi|Ekow Othniel Kwainoe|200
Central|Gomoa Central|Kwame Asare Obeng|200
Central|Gomoa East|Desmond De-graft Paitoo|200
Central|Gomoa West|Richard Gyan Mensah|200
Central|Hemang Lower Denkyira|Lawrence Agyinsam|200
Central|Komenda-Edina-Eguafo-Abirem|Samuel Atta Mills|200
Central|Mfantseman|Ebenezer Prince Arhin|200
Central|Twifo-Atii Morkwaa|David Theophilus Dominic Vondee|200
Central|Upper Denkyira East|Emelia Ankomah|200
Central|Upper Denkyira West|Rudolf Amoako-Gyampah|200
Eastern|Abetifi|Bryan Achemapong|200
Eastern|Abirem|Charles Asuako Owiredu|200
Eastern|Abuakwa North|Nana Ampaw Kwame Addo Frempong|200
Eastern|Abuakwa South|Kingsley Agyemang|200
Eastern|Achiase|Kofi Ahenkorah Marfo|200
Eastern|Afram Plains North|Worlase Kpeli|200
Eastern|Afram Plains South|Joseph Appiah Boateng|200
Eastern|Akim Oda|Alexander Akwasi Acquah|200
Eastern|Akim Swedru|Kennedy Osei Nyarko|200
Eastern|Akropong|Samuel Awuku|200
Eastern|Akwapim South|Lawrencia Dziwornu|200
Eastern|Akwatia|Bernard Bediako Baidoo|200
Eastern|Asene-Akroso-Manso|George Kwame Aboagye|200
Eastern|Asuogyaman|Thomas Nyarko Ampem|200
Eastern|Atiwa East|Abena Osei Asare|200
Eastern|Atiwa West|Laurette Korkor Asante|200
Eastern|Ayensuano|Ida Adjoa Asiedu|200
Eastern|Fanteakwa North|Kwame Appiah Kodua|200
Eastern|Fanteakwa South|Duke Ofori-Atta|200
Eastern|Kade|Alexander Agyare|200
Eastern|Lower Manya Krobo|Ebenezer Okletey Terlabi|200
Eastern|Lower West Akim|Owen Kwame Frimpong|200
Eastern|Mpraeso|Davis Ansah Opoku|200
Eastern|New Juaben North|Nana Osei-Adjei|200
Eastern|New Juaben South|Michael Okyere Baafi|200
Eastern|Nkawkaw|Joseph Frimpong|200
Eastern|Nsawam Adoagyiri|Frank Annoh-Dompreh|300
Eastern|Ofoase-Ayirebi|Kojo Oppong-Nkrumah|200
Eastern|Okere|Daniel Nana Addo Kenneth|200
Eastern|Suhum|Frank Asideu Bekoe|200
Eastern|Upper Manya Krobo|Bismark Tetteh Nyarko|200
Eastern|Upper West Akim|Emmanuel Drah|200
Eastern|Yilo Krobo|Albert Tetteh Nyakotey|200
Greater Accra|Ablekuma Central|Dan Abdul-latif|200
Greater Accra|Ablekuma North|Ewurabena Aubynn|200
Greater Accra|Ablekuma South|Alfred Okoe Vanderpuije|200
Greater Accra|Ablekuma West|Kweku Addo|200
Greater Accra|Ada|Comfort Doyoe Cudjoe-Ghansah|300
Greater Accra|Adenta|Mohammed Adamu Ramadan|200
Greater Accra|Amasaman|Sedem Kweku Afenyo|200
Greater Accra|Anyaa-Sowutuom|Emmanuel Tobim|200
Greater Accra|Ashaiman|Ernest Henry Norgbey|200
Greater Accra|Ayawaso Central|Abdul Rauf Tongym Tubazu|200
Greater Accra|Ayawaso East|Naser Toure Mahama|200
Greater Accra|Ayawaso North|Yussif Issaka Jajah|200
Greater Accra|Ayawaso West Wuogon|John Dumelo|200
Greater Accra|Bortianor-Ngleshie-Amanfro|Felix Akwetey Okle|200
Greater Accra|Dade Kotopon|Rita Naa Odoley Sowah|200
Greater Accra|Dome Kwabenya|Faustina Elikplim Akurugu|200
Greater Accra|Domeabra-Obom|Isaac Awuku Yibor|200
Greater Accra|Korle Klottey|Zanetor Agyeman-Rawlings|200
Greater Accra|Kpone-Katamanso|Joseph Akuerteh Tettey|200
Greater Accra|Krowor|Agnes Naa Momo Lartey|200
Greater Accra|Ledzokuku|Benjamin Ayiku Nartey|200
Greater Accra|Madina|Francis-Xavier Kojo Sosu|200
Greater Accra|Ningo-Prampram|Samuel George Nartey|200
Greater Accra|Odododiodio|Alfred Nii Kotei Ashie|200
Greater Accra|Okaikwei Central|Patrick Yaw Boamah|200
Greater Accra|Okaikwei North|Theresa Lardi Awuni|200
Greater Accra|Okaikwei South|Ernest Adomako|200
Greater Accra|Sege|Daniel Keshi Bessey|200
Greater Accra|Shai-Osudoku|Linda Obenewaa Akweley Ocloo|200
Greater Accra|Tema Central|Charles Forson|200
Greater Accra|Tema East|Isaac Ashai Odamtten|200
Greater Accra|Tema West|James Enu|200
Greater Accra|Trobu|Gloria Owusu|200
Greater Accra|Weija Gbawe|Jerry Ahmed Shaib|300
Northern|Bimbilla|Dominc Aduna Bingab Nitiwul|200
Northern|Gushegu|Alhassan Tampuli Sulemana|200
Northern|Karaga|Mohammed Amin Adam|200
Northern|Kpandai|Matthew Nyindam|200
Northern|Kumbungu|Hamza Adam|200
Northern|Mion|Misbahu Mahama Adams|200
Northern|Nanton|Mohammed Sherif Abdul-Kaliq|200
Northern|Saboba|Joseph Bukari Nikpe|200
Northern|Sagnarigu|Attah Issa|200
Northern|Savelugu|Abdul Aziz Fatahiya|200
Northern|Tamale Central|Professor Alidu Seidu|200
Northern|Tamale North|Suhuyini Alhassan Sayibu|200
Northern|Tamale South|Haruna Iddrisu|200
Northern|Tatale-Sanguli|Ntebe Ayo William|200
Northern|Tolon|Habib Iddrisu|300
Northern|Wulensi|Nandaya Yaw Stanley|200
Northern|Yendi|Alhassan Abdul-Fatawu|200
Northern|Zabzugu|Alhassan Umar|200
North East|Bunkpurugu|Bandim Abed-Nego Azumah|200
North East|Chereponi|Seidu Alhassan Alajor|200
North East|Nalerigu Gambaga|Mumuni Muhammed|200
North East|Walewale|Mahama Tiah Abdul-Kabiru|200
North East|Yagaba-Kubori (Walewale West)|Mustapha Ussif|200
North East|Yunyoo|Alhassan Sulemana|200
Oti|Akan|Yao Gomado|200
Oti|Biakoye|Jean-Marie Formadi|200
Oti|Buem|Iddie Kofi Adams|200
Oti|Guan|Fred Kwesi Agbenyo|200
Oti|Krachi East|Nelson Kofi Djabab|200
Oti|Krachi Nchumuru|Solomon Kuyon|200
Oti|Krachi West|Helen Adjoa Ntoso|200
Oti|Nkwanta North|John Kwabena Bless Oti|200
Oti|Nkwanta South|Geoffrey Kini|200
Savannah|Bole Bamboi|Yusif Sulemana|200
Savannah|Daboya-Mankarigu|Shaibu Mahama|200
Savannah|Damango|Samuel Abu Jinapor|200
Savannah|Salaga North|Alhassan Mumuni|200
Savannah|Salaga South|Zuwera Mohammed Ibrahimah|200
Savannah|Sawla-Tuna-Kalba|Andrew Dari Chiwetey|200
Savannah|Yapei-Kusawgu|John Abdulai Jinapor|200
Upper East|Bawku Central|Mahama Ayariga|300
Upper East|Binduri|Mahmoud Issifu|200
Upper East|Bolgatanga Central|Isaac Adongo|200
Upper East|Bolgatanga East|Dominic Akuritinga Ayine|200
Upper East|Bongo|Charles Bawaduah|200
Upper East|Builsa North|James Agalga|200
Upper East|Builsa South|Clement Apaak|200
Upper East|Chiana-Paga|Nikyema Billa Alamzy|200
Upper East|Garu|Anabah Thomas Winsum|200
Upper East|Nabdam|Mark Kurt Nawaane|200
Upper East|Navrongo Central|Simon Akibange Aworigo|200
Upper East|Pusiga|Laadi Ayii Ayamba|200
Upper East|Talensi|Daniel Dung Mahama|200
Upper East|Tempane|Akanvariva Lydia Lamisi|200
Upper East|Zebilla|Ebenezer Alumire Ndebilla|200
Upper West|Daffiama-Bussie-Issa|Sebastian Ngmenenso Sandaare|200
Upper West|Jirapa|Cletus Seidu Dapilaah|200
Upper West|Lambussie|Titus Kofi Beyuo|200
Upper West|Lawra|Bede A. Zeideng|200
Upper West|Nadowli Kaleo|Sumah Anthony Mwinikaara|200
Upper West|Nandom|Richard Kuuire|200
Upper West|Sissala East|Mohammed Issah Bataglia|200
Upper West|Sissala West|Mohammed Adams Sukparu|200
Upper West|Wa Central|Abdul-Rashid Hassan Pelpuo|200
Upper West|Wa East|Godfred Seidu Jasaw|200
Upper West|Wa West|Peter Lanchene Toobu|200
Volta|Adaklu|Kwame Governs Agbodza|200
Volta|Afadjato South|Frank Afriyie|200
Volta|Agotime-Ziope|Charles Akwesi Agbeve|200
Volta|Akatsi North|Peter Kwasi Nortsu-Kotoe|200
Volta|Akatsi South|Bernard Ahiafor|300
Volta|Anlo|Richard Kwame Sefe|200
Volta|Central Tongu|Alexander Roosevelt Hottordze|200
Volta|Ho Central|Edem Kofi Kpotosu|200
Volta|Ho West|Emmanuel Kwasi Bedzrah|200
Volta|Hohoe|Tsekpo Worlanyo Thomas|200
Volta|Keta|Kwame Dzudzorli Gakpey|200
Volta|Ketu North|Edem Agbana|200
Volta|Ketu South|Dzifa Gomashie|200
Volta|Kpando|Sebastian Deh|200
Volta|North Dayi|Joycelyn Tetteh|200
Volta|North Tongu|Samuel Okudzeto Ablakwa|200
Volta|South Dayi|Rockson-Nelson Etse Dafeamekpor|300
Volta|South Tongu|Maxwell Lukutor|200
Western|Ahanta West|Mavis Kuukua Bissue|200
Western|Amenfi Central|Joana Gyan Cudjoe|200
Western|Amenfi East|Nicholas Amankwah|200
Western|Amenfi West|Eric Afful|200
Western|Effia|Isaac Yaw Boamah-Nyarko|200
Western|Ellembelle|Emmanuel Armah-Kofi Buah|200
Western|Essikado-Ketan|Grace Ayensu-Danquah|200
Western|Evalue-Ajomoro-Gwira|Kofi Arko Nokoe|200
Western|Jomoro|Dorcas Affo-Toffey|200
Western|Kwesimintsim|Philip Fiifi Buckman|200
Western|Mpohor|Bentil Godfred Henry|200
Western|Prestea-Huni Valley|Robert Wisdom Cudjoe|200
Western|Sekondi|Blay Nyameke Armah|200
Western|Shama|Emelia Arthur|200
Western|Takoradi|Kwabena Okyere Darko-Mensah|200
Western|Tarkwa-Nsuaem|Issa Salifu Taylor|200
Western|Wassa East|Isaac Adjei Mensah|200
Western North|Aowin|Oscar Ofori Larbi|200
Western North|Bia East|Richard Acheampong|300
Western North|Bia West|Mustapha Amadu Tanko|200
Western North|Bibiani-Anhwiaso-Bekwai|Bright Asamoah Brefo|200
Western North|Bodi|Sampson Ahi|200
Western North|Juabeso|Kwabena Mintah Akandoh|200
Western North|Sefwi Akontombra|Pious Kwame Nkuah|200
Western North|Sefwi Wiawso|Kofi Benteh Afful|200
Western North|Suaman|Frederick Addy|200"""

rows = [l.split('|') for l in D.strip().splitlines()]
assert len(rows) == 276, len(rows)
total = sum(int(r[3]) for r in rows)
assert total == 56400, total
print(f"{len(rows)} MPs, {total:,} streetlights — both reconcile to the letter.")

def sheet(path, headers, data):
    wb = Workbook(); ws = wb.active; ws.append(headers)
    for r in data: ws.append(r)
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(16, len(h) + 4)
    wb.save(path); print(f"  {path}  ({len(data)} rows)")

sheet('07_members_of_parliament_all_276.xlsx',
      ['title','name','constituency','region','district','email','phone'],
      [['Hon.', n, c, reg, '', '', ''] for reg, c, n, q in rows])

# Gomoa West community — name now matches the roster exactly.
sheet('05_communities_STREETLIGHTS_gomoa_west.xlsx',
      ['region','district','community','constituency','mp_name'],
      [['Central','Gomoa West','Gomoa West','Gomoa West','Richard Gyan Mensah']])
