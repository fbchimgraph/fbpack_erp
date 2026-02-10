from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.shortcuts import render
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import pandas as pd
import datetime
import re
from .models import *

# --- VUES EXISTANTES (DASHBOARD & REPORTING) ---

@login_required
def dashboard(request):
    # KPIs globaux
    context = {
        'count_clients': Client.objects.count(),
        'count_of_running': ProductionOrder.objects.filter(status='IN_PROGRESS').count(),
        'low_stock_count': len([m for m in Material.objects.all() if m.is_low_stock()]),
        'machines': Machine.objects.all(),
        'orders_per_machine': ProductionOrder.objects.values('machine__name').annotate(count=Count('id')),
    }
    return render(request, 'dashboard.html', context)

@login_required
def production_gantt(request):
    orders = ProductionOrder.objects.exclude(status='DONE').order_by('machine', 'start_time')
    return render(request, 'production/gantt.html', {'orders': orders})

@login_required
def reporting(request):
    delayed_ofs = ProductionOrder.objects.filter(status='LATE')
    
    top_clients = ProductionOrder.objects.values('client__name').annotate(
        total_kg=Sum('produced_qty')
    ).order_by('-total_kg')[:5]
    
    top_consumptions = ConsumptionLog.objects.values('material__name').annotate(
        total_used=Sum('quantity_used')
    ).order_by('-total_used')[:5]

    context = {
        'delayed_ofs': delayed_ofs,
        'top_clients_labels': [c['client__name'] for c in top_clients],
        'top_clients_data': [c['total_kg'] for c in top_clients],
        'top_consumptions_labels': [c['material__name'] for c in top_consumptions],
        'top_consumptions_data': [c['total_used'] for c in top_consumptions],
    }
    return render(request, 'reporting.html', context)


# --- NOUVELLE VUE D'IMPORTATION UNIFIÉE ---

@login_required
def import_stock_view(request):
    context = {}
    
    # Début du bloc TRY pour attraper les erreurs
    if request.method == 'POST' and request.FILES.get('excel_file'):
        try:
            import_type = request.POST.get('import_type')
            excel_file = request.FILES['excel_file']
            fs = FileSystemStorage()
            filename = fs.save(excel_file.name, excel_file)
            file_path = fs.path(filename)
            
            # Lecture Excel (fillna pour éviter les NaN qui plantent les calculs)
            df = pd.read_excel(file_path).fillna(0)
            count = 0
            
            # --- 1. IMPORT STOCK ---
            if import_type == 'STOCK':
                for _, row in df.iterrows():
                    cat_map = {'Film': 'FILM', 'Encre': 'INK', 'Colle': 'GLUE', 'Solvant': 'SOLV'}
                    cat_raw = row.get('Categorie', 'FILM')
                    if cat_raw == 0: cat_raw = 'FILM'
                    
                    Material.objects.update_or_create(
                        name=row.get('Designation', 'Inconnu'),
                        defaults={
                            'category': cat_map.get(cat_raw, 'FILM'),
                            'quantity': row.get('Quantite', 0),
                            'unit': row.get('Unite', 'kg'),
                            'min_threshold': row.get('Seuil_Min', 0),
                            'price_per_unit': row.get('Prix', 0)
                        }
                    )
                    count += 1

            # --- 2. IMPORT CRM ---
            elif import_type == 'CRM':
                for _, row in df.iterrows():
                    status_map = {'Active': 'ACTIVE', 'Prospect': 'PROSPECT', 'VIP': 'VIP'}
                    nom = row.get('Nom')
                    if nom and nom != 0:
                        Client.objects.update_or_create(
                            name=nom,
                            defaults={
                                'city': row.get('Ville', ''),
                                'phone': row.get('Telephone', ''),
                                'email': row.get('Email', ''),
                                'sector': row.get('Secteur', ''),
                                'status': status_map.get(row.get('Statut'), 'PROSPECT')
                            }
                        )
                        count += 1

            # --- 3. IMPORT OUTILLAGE ---
            elif import_type == 'TOOLS':
                def clean_val(v):
                    if pd.isna(v) or v == '' or v is None: return 0
                    return v
                
                user_default_type = request.POST.get('default_tool_type', 'CYL')

                for index, row in df.iterrows():
                    serial_val = None
                    for col in df.columns:
                        c_upper = str(col).upper()
                        if "CLYCH" in c_upper or "CLICH" in c_upper:
                            serial_val = row.get(col)
                            break
                    
                    if pd.isna(serial_val) and "CODE" in df.columns: serial_val = row.get('CODE')
                    if pd.isna(serial_val) or serial_val == '' or serial_val == 0: continue

                    serial = str(serial_val).strip()
                    code_interne = row.get('CODE')
                    if not code_interne or code_interne == 0: code_interne = serial
                    
                    client_name = row.get('CLIENT')
                    if not client_name or client_name == 0: client_name = "Client Inconnu"

                    designation = str(row.get('DESIGNATIONS', '')).upper()

                    final_tool_type = user_default_type
                    if 'FLEXO' in designation: final_tool_type = 'CLICHE'

                    # Couleurs
                    clr_col = next((c for c in df.columns if 'CLR' in c or 'COUL' in c), None)
                    raw_clr = str(row.get(clr_col, '0')) if clr_col else '0'
                    try:
                        nb_colors = int(re.search(r'\d+', raw_clr).group())
                    except:
                        nb_colors = 0

                    dev_col = next((c for c in df.columns if 'DEV' in c), None)
                    dev_mm = clean_val(row.get(dev_col)) if dev_col else 0

                    met_col = next((c for c in df.columns if 'METRAGE' in c or '(ML)' in c), None)
                    metrage_ml = clean_val(row.get(met_col)) if met_col else 0
                    laize_val = clean_val(row.get('LAIZE'))

                    client, _ = Client.objects.get_or_create(name=client_name)
                    product, _ = TechnicalProduct.objects.get_or_create(
                        ref_internal=code_interne,
                        defaults={
                            'name': designation, 'client': client, 'structure_type': 'MONO',
                            'width_mm': laize_val, 'cut_length_mm': dev_mm, 'num_colors': nb_colors
                        }
                    )
                    product.cut_length_mm = dev_mm
                    product.num_colors = nb_colors
                    product.save()

                    tours = 0
                    try:
                        if float(dev_mm) > 0:
                            tours = int(float(metrage_ml) / (float(dev_mm) * 0.001))
                    except:
                        tours = 0

                    Tooling.objects.update_or_create(
                        serial_number=serial,
                        defaults={
                            'product': product, 'tool_type': final_tool_type,
                            'current_impressions': tours, 'max_impressions': 2000000
                        }
                    )
                    count += 1

            # --- 4. IMPORT PLANNING ---
            elif import_type == 'PLANNING':
                for _, row in df.iterrows():
                    cli_name = row.get('Client')
                    if cli_name and cli_name != 0:
                        client, _ = Client.objects.get_or_create(name=cli_name)
                        prod_name = row.get('Produit')
                        product, _ = TechnicalProduct.objects.get_or_create(
                            ref_internal=f"REF-{str(prod_name)[:5]}", 
                            defaults={'name': prod_name, 'client': client, 'structure_type': 'MONO', 'width_mm': 500}
                        )
                        mac_name = row.get('Machine')
                        machine = Machine.objects.filter(name__icontains=str(mac_name)).first()
                        try:
                            start_d = pd.to_datetime(row.get('Date_Debut'))
                        except:
                            start_d = datetime.datetime.now()
                        end_d = start_d + datetime.timedelta(hours=4)
                        
                        ProductionOrder.objects.update_or_create(
                            of_number=str(row.get('OF_Numero')),
                            defaults={
                                'client': client, 'product': product, 'machine': machine,
                                'start_time': start_d, 'end_time': end_d,
                                'quantity_planned': row.get('Qte_Prevue', 0), 'status': 'PLANNED'
                            }
                        )
                        count += 1

            # --- 5. IMPORT CONSOMMATION (AVEC JOB & GRAMMAGE) ---
            elif import_type == 'CONSO':
                for _, row in df.iterrows():
                    # 1. Date
                    try:
                        d_prod = pd.to_datetime(row.get('Date')).date()
                    except:
                        d_prod = datetime.date.today()

                    # 2. Type
                    raw_type = str(row.get('Type', 'FLEXO')).upper()
                    final_type = 'HELIO' if 'HELIO' in raw_type else 'FLEXO'

                    # 3. Nom du Job (Essaye plusieurs colonnes)
                    job_val = row.get('Job')
                    if not job_val: job_val = row.get('Nom')
                    if not job_val: job_val = row.get('Designation')
                    if not job_val: job_val = "Inconnu"

                    # 4. Création
                    ConsommationEncre.objects.create(
                        job_name=str(job_val),
                        date=d_prod,
                        process_type=final_type,
                        support=row.get('Support', 'Inconnu'),
                        laize=float(row.get('Laize', 0)),
                        
                        # Récupération sécurisée des poids pour le calcul du grammage
                        bobine_in=float(row.get('Bobine_In', 0)),
                        bobine_out=float(row.get('Bobine_Out', 0)),
                        metrage=float(row.get('Metrage', 0)),
                        
                        encre_noir=float(row.get('Noir', 0)),
                        encre_magenta=float(row.get('Magenta', 0)),
                        encre_jaune=float(row.get('Jaune', 0)),
                        encre_cyan=float(row.get('Cyan', 0)),
                        encre_dore=float(row.get('Dore', 0)),
                        encre_silver=float(row.get('Silver', 0)),
                        encre_orange=float(row.get('Orange', 0)),
                        encre_blanc=float(row.get('Blanc', 0)),
                        encre_vernis=float(row.get('Vernis', 0)),
                        
                        solvant_metoxyn=float(row.get('Metoxyn', 0)),
                        solvant_2080=float(row.get('2080', 0))
                    )
                    count += 1

            # SUCCÈS
            context = {'message': f'✅ Succès ! {count} lignes importées dans {import_type}.', 'success': True}
            
        except Exception as e:
            # ERREUR (C'est ce bloc qui manquait !)
            context = {'message': f'❌ Erreur : {str(e)}', 'success': False}
            
    return render(request, 'stock/import_stock.html', context)