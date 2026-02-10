from django.db import models
from django.utils import timezone
import datetime

# --- A. CRM ---
class Client(models.Model):
    STATUS_CHOICES = [('PROSPECT', 'Prospect'), ('ACTIVE', 'Actif'), ('VIP', 'VIP'), ('LOST', 'Perdu')]
    name = models.CharField("Raison Sociale", max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PROSPECT')
    sector = models.CharField("Secteur", max_length=100, blank=True)
    city = models.CharField("Ville", max_length=100)
    phone = models.CharField("Téléphone", max_length=50)
    email = models.EmailField(blank=True)
    
    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"

    def __str__(self): return self.name

class ClientContact(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    name = models.CharField("Nom", max_length=100)
    role = models.CharField("Fonction", max_length=100)
    is_primary = models.BooleanField("Principal", default=False)
    
    class Meta:
        verbose_name = "Contact Client"
        verbose_name_plural = "Contacts Clients"

class InteractionLog(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    date = models.DateTimeField(default=timezone.now)
    type = models.CharField(max_length=50, choices=[('CALL', 'Appel'), ('EMAIL', 'Email'), ('MEET', 'Rdv')])
    summary = models.CharField("Résumé", max_length=200)
    details = models.TextField("Détails")

    class Meta:
        verbose_name = "Journal d'interaction"
        verbose_name_plural = "Journaux d'interaction"

# --- B. PREPRESSE (Fiches Techniques & Outillage) ---
class TechnicalProduct(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    ref_internal = models.CharField("Ref Interne", max_length=50, unique=True)
    name = models.CharField("Désignation", max_length=200)
    
    # Structure
    structure_type = models.CharField(max_length=20, choices=[('MONO', 'Mono'), ('DUPLEX', 'Duplex'), ('TRIPLEX', 'Triplex')], default='MONO')
    width_mm = models.FloatField("Laize (mm)", default=0)
    
    # Anti-Crash: On autorise le vide
    cut_length_mm = models.FloatField("Pas de coupe (mm)", default=0, null=True, blank=True)
    num_colors = models.IntegerField("Nb Couleurs", default=0, null=True, blank=True)
    
    # Fichiers
    artwork_file = models.FileField("Fichier Graphique (AI/PDF)", upload_to='artwork/', blank=True)
    artwork_version = models.IntegerField(default=1)
    
    class Meta:
        verbose_name = "Produit technique"
        verbose_name_plural = "Produits techniques"

    def __str__(self): return f"{self.ref_internal} - {self.name}"

class Tooling(models.Model):
    TYPE_CHOICES = [('CYL', 'Cylindre Hélio'), ('CLICHE', 'Cliché Flexo')]
    product = models.ForeignKey(TechnicalProduct, on_delete=models.CASCADE)
    tool_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    serial_number = models.CharField("N° Série", max_length=100)
    
    # Usure
    max_impressions = models.IntegerField("Durée de vie (tours)", default=1000000)
    current_impressions = models.IntegerField("Tours actuels", default=0)
    
    class Meta:
        verbose_name = "Outillage cliché, cylindre"         
        verbose_name_plural = "Outillages cliché, cylindre"

    def wear_percent(self):
        if self.max_impressions == 0: return 0
        return round((self.current_impressions / self.max_impressions) * 100, 1)

# --- E. STOCK (Matières Premières) ---
class Supplier(models.Model):
    name = models.CharField("Fournisseur", max_length=200)
    email = models.EmailField()

    class Meta:
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"

    def __str__(self): return self.name

class Material(models.Model):
    CAT_CHOICES = [('FILM', 'Film/Papier'), ('INK', 'Encre'), ('GLUE', 'Colle'), ('SOLV', 'Solvant')]
    name = models.CharField("Désignation", max_length=200)
    category = models.CharField(max_length=10, choices=CAT_CHOICES)
    quantity = models.FloatField("Stock Réel")
    unit = models.CharField("Unité", max_length=10, default='kg')
    min_threshold = models.FloatField("Stock Alerte (Min)")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True)
    price_per_unit = models.DecimalField("Prix Unitaire", max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Matière première"
        verbose_name_plural = "Matières premières"

    def is_low_stock(self):
        return self.quantity <= self.min_threshold

    def __str__(self): return self.name

# --- D. MACHINES & MAINTENANCE ---
class Machine(models.Model):
    STATUS_CHOICES = [('RUN', 'En Production'), ('STOP', 'Arrêt'), ('MAINT', 'Maintenance'), ('PANNE', 'En Panne')]
    name = models.CharField("Nom Machine", max_length=100)
    type = models.CharField(max_length=50, choices=[('EXT', 'Extrudeuse'), ('IMP', 'Imprimeuse'), ('DEC', 'Découpeuse')])
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='STOP')

    class Meta:
        verbose_name = "Machine"
        verbose_name_plural = "Machines"

    def __str__(self): return self.name

class MaintenanceSchedule(models.Model):
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE)
    task = models.CharField("Tâche", max_length=200)
    frequency_days = models.IntegerField("Fréquence (jours)")
    last_done = models.DateField("Dernière fois")
    
    class Meta:
        verbose_name = "Planning Maintenance"
        verbose_name_plural = "Plannings Maintenance"

    @property
    def next_due(self):
        return self.last_done + datetime.timedelta(days=self.frequency_days)

class IncidentLog(models.Model):
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    issue = models.CharField("Panne", max_length=200)
    action_taken = models.TextField("Action Corrective")
    downtime_minutes = models.IntegerField("Temps d'arrêt (min)", default=0)

    class Meta:
        verbose_name = "Journal d'incident"
        verbose_name_plural = "Journaux d'incidents"

# --- C. PRODUCTION (Planning & OF) ---
class ProductionOrder(models.Model):
    of_number = models.CharField("N° OF", max_length=50, unique=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    product = models.ForeignKey(TechnicalProduct, on_delete=models.CASCADE)
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True)
    
    quantity_planned = models.FloatField("Qté Prévue (kg/m)")
    start_time = models.DateTimeField("Début Prévu")
    end_time = models.DateTimeField("Fin Prévue")
    
    status = models.CharField(max_length=20, default='PLANNED', choices=[('PLANNED', 'Planifié'), ('IN_PROGRESS', 'En cours'), ('DONE', 'Terminé'), ('LATE', 'En Retard')])
    
    # BAT Link
    bat_file = models.FileField("BAT Validé", upload_to='bat/', blank=True, null=True)
    
    # Real Time Data (Saisi par l'opérateur)
    produced_qty = models.FloatField("Qté Produite", default=0)
    waste_qty = models.FloatField("Déchets (kg)", default=0)
    
    class Meta:
        verbose_name = "Ordre de fabrication"
        verbose_name_plural = "Ordres de fabrication"

    def __str__(self): return f"OF {self.of_number} - {self.product.name}"

class ConsumptionLog(models.Model):
    of = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='consumptions')
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    quantity_used = models.FloatField("Qté Consommée")
    
    def save(self, *args, **kwargs):
        # Décrémente le stock automatiquement
        self.material.quantity -= self.quantity_used
        self.material.save()
        super().save(*args, **kwargs)

class PurchaseOrder(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, default='DRAFT', choices=[('DRAFT', 'Brouillon'), ('SENT', 'Envoyée'), ('RECEIVED', 'Reçue')])
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Bon de commande"
        verbose_name_plural = "Bons de commande"

class Quote(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    reference = models.CharField("Référence", max_length=50)
    date = models.DateField(default=timezone.now)
    total_amount = models.DecimalField("Montant Total", max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, default='DRAFT', choices=[('DRAFT', 'Brouillon'), ('SENT', 'Envoyé'), ('SIGNED', 'Signé')])
    pdf_file = models.FileField("PDF Signé", upload_to='quotes/', blank=True, null=True)

    class Meta:
        verbose_name = "Devis"
        verbose_name_plural = "Devis"

    def __str__(self): return self.reference

class ConsommationEncre(models.Model):
    PROCESS_CHOICES = [('FLEXO', 'Flexo'), ('HELIO', 'Hélio')]

    # Infos Générales (AJOUT DE JOB_NAME EN PREMIER)
    job_name = models.CharField("Nom du Job", max_length=200, default="Sans Nom")
    date = models.DateField("Date De Prod", default=timezone.now)
    process_type = models.CharField("Type Process", max_length=10, choices=PROCESS_CHOICES, default='FLEXO')
    support = models.CharField("Support", max_length=100)
    laize = models.FloatField("Laize (mm)", default=0)
    
    # Poids Bobines
    bobine_in = models.FloatField("Total Bobine In (kg)", default=0)
    bobine_out = models.FloatField("Total Bobine Out (kg)", default=0)
    metrage = models.FloatField("Métrage (m)", default=0)

    # Encres
    encre_noir = models.FloatField("Noir", default=0)
    encre_magenta = models.FloatField("Magenta", default=0)
    encre_jaune = models.FloatField("Jaune", default=0)
    encre_cyan = models.FloatField("Cyan", default=0)
    encre_dore = models.FloatField("Doré", default=0)
    encre_silver = models.FloatField("Silver", default=0)
    encre_orange = models.FloatField("Orange", default=0)
    encre_blanc = models.FloatField("Blanc", default=0)
    encre_vernis = models.FloatField("Vernis Anti", default=0)

    # Solvants
    solvant_metoxyn = models.FloatField("Metoxyn", default=0)
    solvant_2080 = models.FloatField("20/80", default=0)

    class Meta:
        verbose_name = "Conso. Encre & Solvant"
        verbose_name_plural = "Conso. Encres & Solvants"

    def __str__(self):
        return f"{self.job_name} - {self.date}"

    # --- FORMULES ---

    @property
    def total_encre(self):
        return (self.encre_noir + self.encre_magenta + self.encre_jaune + 
                self.encre_cyan + self.encre_dore + self.encre_silver + 
                self.encre_orange + self.encre_blanc + self.encre_vernis)

    @property
    def total_solvant(self):
        return self.solvant_metoxyn + self.solvant_2080

    @property
    def gain_de_masse_kg(self):
        # Si les bobines ne sont pas remplies, le gain est 0
        return round(self.bobine_out - self.bobine_in, 2)

    @property
    def matiere_evaporee_kg(self):
        total_injecte = self.total_encre + self.total_solvant
        return round(total_injecte - self.gain_de_masse_kg, 2)

    @property
    def gain_de_masse_percent(self):
        total_injecte = self.total_encre + self.total_solvant
        if total_injecte == 0: return 0
        return round((self.gain_de_masse_kg / total_injecte) * 100, 2)

    @property
    def matiere_evaporee_percent(self):
        total_injecte = self.total_encre + self.total_solvant
        if total_injecte == 0: return 0
        return round((self.matiere_evaporee_kg / total_injecte) * 100, 2)

    @property
    def grammage(self):
        # Formule : (GainMasse * 1000) / Surface_m2
        # Surface = Metrage * (Laize_mm / 1000)
        surface = self.metrage * (self.laize / 1000)
        if surface == 0: return 0
        return round((self.gain_de_masse_kg * 1000) / surface, 2)