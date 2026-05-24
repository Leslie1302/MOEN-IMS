"""
Django management command to populate Ghana's regions and districts.

Usage:
    python manage.py populate_geospatial_data

This command creates:
- Ghana's 16 administrative regions
- All districts within each region
"""

from django.core.management.base import BaseCommand
from Inventory.models import Region, District

# Ghana's 16 regions with their districts
GHANA_DATA = {
    'Ashanti': {
        'code': 'ASH',
        'capital': 'Kumasi',
        'population': 4780382,
        'districts': [
            {'name': 'Kumasi Metropolitan', 'code': 'KMA'},
            {'name': 'Adum', 'code': 'ADM'},
            {'name': 'Asante Akim North', 'code': 'AAN'},
            {'name': 'Asante Akim South', 'code': 'AAS'},
            {'name': 'Atwima Kwanwoma', 'code': 'AKW'},
            {'name': 'Atwima Mponua', 'code': 'AMP'},
            {'name': 'Atwima Nwabiagya North', 'code': 'ANN'},
            {'name': 'Atwima Nwabiagya South', 'code': 'ANS'},
            {'name': 'Bosomtwe', 'code': 'BOS'},
            {'name': 'Ejisu-Juansa', 'code': 'EJU'},
            {'name': 'Kwabre East', 'code': 'KWE'},
        ]
    },
    'Greater Accra': {
        'code': 'GA',
        'capital': 'Accra',
        'population': 4914127,
        'districts': [
            {'name': 'Accra Metropolitan', 'code': 'AMA'},
            {'name': 'Ada East', 'code': 'ADE'},
            {'name': 'Ada West', 'code': 'ADW'},
            {'name': 'Ga Central', 'code': 'GAC'},
            {'name': 'Ga East', 'code': 'GAE'},
            {'name': 'Ga South', 'code': 'GAS'},
            {'name': 'Ga West', 'code': 'GAW'},
            {'name': 'Lajide', 'code': 'LAJ'},
            {'name': 'Tema Metropolitan', 'code': 'TMA'},
        ]
    },
    'Western': {
        'code': 'WR',
        'capital': 'Sekondi-Takoradi',
        'population': 2380461,
        'districts': [
            {'name': 'Sekondi-Takoradi Metropolitan', 'code': 'STM'},
            {'name': 'Ahanta West', 'code': 'AHW'},
            {'name': 'Axim', 'code': 'AXM'},
            {'name': 'Dix Cove', 'code': 'DIX'},
            {'name': 'Enchi', 'code': 'ENH'},
            {'name': 'Juaso', 'code': 'JUA'},
            {'name': 'Prestea Huni Valley', 'code': 'PHV'},
            {'name': 'Sefwi Akontombra', 'code': 'SAK'},
            {'name': 'Tarkwa Nsuaem', 'code': 'TAN'},
            {'name': 'Wassa Amenakrom', 'code': 'WAM'},
            {'name': 'Wassa East', 'code': 'WAE'},
        ]
    },
    'Central': {
        'code': 'CR',
        'capital': 'Cape Coast',
        'population': 2176498,
        'districts': [
            {'name': 'Cape Coast Metropolitan', 'code': 'CCM'},
            {'name': 'Abura Asebu Kwamankese', 'code': 'AAK'},
            {'name': 'Agona East', 'code': 'AGE'},
            {'name': 'Agona West', 'code': 'AGW'},
            {'name': 'Asikuma Odoben Brakwa', 'code': 'AOB'},
            {'name': 'Assin North', 'code': 'ASN'},
            {'name': 'Assin South', 'code': 'ASS'},
            {'name': 'Awutu Senya East', 'code': 'ASE'},
            {'name': 'Awutu Senya West', 'code': 'ASW'},
            {'name': 'Essikado Ketan', 'code': 'ESK'},
            {'name': 'Komenda Edina Eguafo Abirem', 'code': 'KEA'},
            {'name': 'Twifo Heman Lower Denkyira', 'code': 'THD'},
        ]
    },
    'Eastern': {
        'code': 'ER',
        'capital': 'Koforidua',
        'population': 2633154,
        'districts': [
            {'name': 'Koforidua', 'code': 'KOF'},
            {'name': 'Abuakwa North', 'code': 'ABN'},
            {'name': 'Abuakwa South', 'code': 'ABS'},
            {'name': 'Akuapim North', 'code': 'AKN'},
            {'name': 'Akuapim South', 'code': 'AKS'},
            {'name': 'Akim Central', 'code': 'AKC'},
            {'name': 'Akim North', 'code': 'AKN'},
            {'name': 'Akim South East', 'code': 'AKE'},
            {'name': 'Akim South West', 'code': 'AKW'},
            {'name': 'Ayensuano', 'code': 'AYE'},
            {'name': 'East Akim', 'code': 'EAK'},
            {'name': 'Fanteakwa North', 'code': 'FAN'},
            {'name': 'Fanteakwa South', 'code': 'FAS'},
            {'name': 'Kwaebibirem', 'code': 'KWA'},
            {'name': 'Lower Manya Krobo', 'code': 'LMK'},
            {'name': 'New Juansa', 'code': 'NJU'},
            {'name': 'Suhum', 'code': 'SUH'},
            {'name': 'Upper Manya Krobo', 'code': 'UMK'},
            {'name': 'West Akim', 'code': 'WAK'},
        ]
    },
    'Volta': {
        'code': 'VR',
        'capital': 'Ho',
        'population': 1932354,
        'districts': [
            {'name': 'Ho Municipal', 'code': 'HOM'},
            {'name': 'Adaklu', 'code': 'ADA'},
            {'name': 'Afadjato South', 'code': 'AFS'},
            {'name': 'Agortime Ziope', 'code': 'AGZ'},
            {'name': 'Ashaiman', 'code': 'ASA'},
            {'name': 'Central Tongu', 'code': 'CNT'},
            {'name': 'East Tongu', 'code': 'ETG'},
            {'name': 'Ho West', 'code': 'HOW'},
            {'name': 'Kadjebi', 'code': 'KAD'},
            {'name': 'Keta', 'code': 'KET'},
            {'name': 'Ketu North', 'code': 'KTN'},
            {'name': 'Ketu South', 'code': 'KTS'},
            {'name': 'North Dayi', 'code': 'NDY'},
            {'name': 'North Tongu', 'code': 'NTG'},
            {'name': 'South Dayi', 'code': 'SDY'},
            {'name': 'South Tongu', 'code': 'STG'},
        ]
    },
    'Northern': {
        'code': 'NR',
        'capital': 'Tamale',
        'population': 2469146,
        'districts': [
            {'name': 'Tamale Metropolitan', 'code': 'TAM'},
            {'name': 'Akuapem North', 'code': 'AKN'},
            {'name': 'Bawku', 'code': 'BAW'},
            {'name': 'Bawku West', 'code': 'BWE'},
            {'name': 'Bolgatanga', 'code': 'BOL'},
            {'name': 'Bolgatanga Municipal', 'code': 'BOM'},
            {'name': 'Builsa North', 'code': 'BUN'},
            {'name': 'Builsa South', 'code': 'BUS'},
            {'name': 'Bunkpurugu Yunyoo', 'code': 'BUY'},
            {'name': 'Chereponi', 'code': 'CHE'},
            {'name': 'Damongo', 'code': 'DAM'},
            {'name': 'Gushegu', 'code': 'GUS'},
            {'name': 'Karaga', 'code': 'KAR'},
            {'name': 'Kasena-Nankana', 'code': 'KAS'},
            {'name': 'Kasena-Nankana East', 'code': 'KAE'},
            {'name': 'Kasena-Nankana West', 'code': 'KAW'},
            {'name': 'Kumbungu', 'code': 'KUM'},
            {'name': 'Mamprugu Moagduri', 'code': 'MAM'},
            {'name': 'Mion', 'code': 'MIO'},
            {'name': 'Savelugu', 'code': 'SAV'},
            {'name': 'Sarigu', 'code': 'SAR'},
            {'name': 'Tamale North', 'code': 'TAN'},
            {'name': 'Zabzugu', 'code': 'ZAB'},
        ]
    },
    'Upper East': {
        'code': 'UE',
        'capital': 'Bolgatanga',
        'population': 1176721,
        'districts': [
            {'name': 'Bolgatanga', 'code': 'BOL'},
            {'name': 'Kasena Nankana', 'code': 'KAS'},
            {'name': 'Bawku', 'code': 'BAW'},
            {'name': 'Pusiga', 'code': 'PUS'},
            {'name': 'Binduri', 'code': 'BIN'},
            {'name': 'Garu-Tempane', 'code': 'GAR'},
        ]
    },
    'Upper West': {
        'code': 'UW',
        'capital': 'Wa',
        'population': 702101,
        'districts': [
            {'name': 'Wa Municipal', 'code': 'WAM'},
            {'name': 'Nadowli Kaleo', 'code': 'NAK'},
            {'name': 'Jirapa Lambussie', 'code': 'JIL'},
            {'name': 'Lawra Nandom', 'code': 'LAN'},
            {'name': 'Sissala East', 'code': 'SIE'},
            {'name': 'Sissala West', 'code': 'SIW'},
        ]
    },
    'Bono': {
        'code': 'BO',
        'capital': 'Sunyani',
        'population': 1239598,
        'districts': [
            {'name': 'Sunyani Municipal', 'code': 'SUM'},
            {'name': 'Berekum', 'code': 'BER'},
            {'name': 'Berekum East', 'code': 'BEE'},
            {'name': 'Dormaa Central', 'code': 'DOC'},
            {'name': 'Dormaa East', 'code': 'DOE'},
            {'name': 'Jaman North', 'code': 'JAN'},
            {'name': 'Jaman South', 'code': 'JAS'},
            {'name': 'Sunyani West', 'code': 'SUW'},
            {'name': 'Tain', 'code': 'TAI'},
        ]
    },
    'Bono East': {
        'code': 'BE',
        'capital': 'Techiman',
        'population': 1312437,
        'districts': [
            {'name': 'Techiman Municipal', 'code': 'TEM'},
            {'name': 'Atebubu Amantin', 'code': 'ATA'},
            {'name': 'Kintampo North', 'code': 'KIN'},
            {'name': 'Kintampo South', 'code': 'KIS'},
            {'name': 'New Edubiase', 'code': 'NED'},
            {'name': 'Nkoranza North', 'code': 'NKN'},
            {'name': 'Nkoranza South', 'code': 'NKS'},
            {'name': 'Sekyere East', 'code': 'SEE'},
            {'name': 'Sekyere West', 'code': 'SEW'},
        ]
    },
    'Ahafo': {
        'code': 'AH',
        'capital': 'Goaso',
        'population': 595261,
        'districts': [
            {'name': 'Asutifi North', 'code': 'ASN'},
            {'name': 'Asutifi South', 'code': 'ASS'},
            {'name': 'Asunafo North', 'code': 'AUN'},
            {'name': 'Asunafo South', 'code': 'AUS'},
        ]
    },
    'Savannah': {
        'code': 'SV',
        'capital': 'Damongo',
        'population': 497590,
        'districts': [
            {'name': 'Central Gonja', 'code': 'CGO'},
            {'name': 'East Gonja', 'code': 'EGO'},
            {'name': 'North Gonja', 'code': 'NGO'},
            {'name': 'West Gonja', 'code': 'WGO'},
        ]
    },
    'North East': {
        'code': 'NE',
        'capital': 'Nalerigu',
        'population': 446050,
        'districts': [
            {'name': 'Bunkpurugu Yunyoo', 'code': 'BUY'},
            {'name': 'Chereponi', 'code': 'CHE'},
        ]
    },
    'Oti': {
        'code': 'OT',
        'capital': 'Dambai',
        'population': 717428,
        'districts': [
            {'name': 'Krachi East', 'code': 'KRE'},
            {'name': 'Krachi West', 'code': 'KRW'},
            {'name': 'Nkwanta North', 'code': 'NKN'},
            {'name': 'Nkwanta South', 'code': 'NKS'},
            {'name': 'Oti Amantin', 'code': 'OAM'},
        ]
    },
    'Western North': {
        'code': 'WN',
        'capital': 'Sefwi Wiawso',
        'population': 569132,
        'districts': [
            {'name': 'Bibiani Anhwiaso Bekwai', 'code': 'BAB'},
            {'name': 'Juasso', 'code': 'JUA'},
            {'name': 'Sefwi Akontombra', 'code': 'SAK'},
            {'name': 'Sefwi Wiawso', 'code': 'SEW'},
        ]
    }
}


class Command(BaseCommand):
    help = 'Populate Ghana regions and districts data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before populating',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing regions and districts...')
            Region.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Cleared existing data'))

        self.stdout.write('Populating Ghana regions and districts...')

        created_count = 0
        skipped_count = 0

        for region_name, region_data in GHANA_DATA.items():
            # Create or get region
            region, created = Region.objects.get_or_create(
                name=region_name,
                defaults={
                    'code': region_data['code'],
                    'capital': region_data['capital'],
                    'population': region_data['population'],
                }
            )

            if created:
                created_count += 1
                self.stdout.write(f'Created region: {region_name}')
            else:
                skipped_count += 1

            # Create districts
            for district_data in region_data['districts']:
                district, district_created = District.objects.get_or_create(
                    region=region,
                    name=district_data['name'],
                    defaults={
                        'code': district_data['code'],
                    }
                )

                if district_created:
                    created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully populated data! Created: {created_count}, Skipped: {skipped_count}'
            )
        )
