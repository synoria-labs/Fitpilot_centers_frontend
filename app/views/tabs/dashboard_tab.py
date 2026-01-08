"""
Vista de la pestaña Dashboard con métricas y gráficas.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QFrame, QGridLayout, QPushButton, QComboBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from ...core import get_logger

logger = get_logger(__name__)

class DashboardTab(QWidget):
    """Vista del dashboard con métricas principales."""
    
    # Señales
    refresh_requested = Signal()
    export_requested = Signal(str)  # format
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.load_metrics()
        
        # Auto-refresh cada 60 segundos
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.load_metrics)
        self.refresh_timer.start(60000)
    
    def setup_ui(self):
        """Configura la interfaz de usuario."""
        layout = QVBoxLayout(self)
        
        # Header con título y controles
        header_layout = QHBoxLayout()
        
        title = QLabel("Dashboard - Métricas Principales")
        title_font = QFont("Arial", 16, QFont.Bold)
        title.setFont(title_font)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Selector de período
        period_label = QLabel("Período:")
        header_layout.addWidget(period_label)
        
        self.period_combo = QComboBox()
        self.period_combo.addItems(["Hoy", "Esta Semana", "Este Mes", "Este Año"])
        self.period_combo.currentTextChanged.connect(self.on_period_changed)
        header_layout.addWidget(self.period_combo)
        
        # Botón de refresh
        refresh_btn = QPushButton("🔄 Actualizar")
        refresh_btn.clicked.connect(self.load_metrics)
        header_layout.addWidget(refresh_btn)
        
        # Botón de exportar
        export_btn = QPushButton("📥 Exportar")
        export_btn.clicked.connect(lambda: self.export_requested.emit("pdf"))
        header_layout.addWidget(export_btn)
        
        layout.addLayout(header_layout)
        
        # Grid de métricas principales
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(15)
        
        # Crear tarjetas de métricas
        self.metric_cards = {
            'total_members': self.create_metric_card("Socios Totales", "0", "👥", "#3498db"),
            'active_members': self.create_metric_card("Socios Activos", "0", "✅", "#2ecc71"),
            'monthly_income': self.create_metric_card("Ingresos del Mes", "$0", "💰", "#f39c12"),
            'today_reservations': self.create_metric_card("Reservas Hoy", "0", "📅", "#e74c3c"),
            'avg_occupancy': self.create_metric_card("Ocupación Promedio", "0%", "📊", "#9b59b6"),
            'new_members': self.create_metric_card("Nuevos Socios", "0", "🆕", "#1abc9c")
        }
        
        # Agregar tarjetas al grid (2 filas x 3 columnas)
        positions = [
            ('total_members', 0, 0),
            ('active_members', 0, 1),
            ('monthly_income', 0, 2),
            ('today_reservations', 1, 0),
            ('avg_occupancy', 1, 1),
            ('new_members', 1, 2)
        ]
        
        for key, row, col in positions:
            metrics_grid.addWidget(self.metric_cards[key], row, col)
        
        layout.addLayout(metrics_grid)
        
        # Sección de gráficas (placeholder)
        charts_label = QLabel("Gráficas")
        charts_font = QFont("Arial", 14, QFont.Bold)
        charts_label.setFont(charts_font)
        layout.addWidget(charts_label)
        
        # Container para gráficas
        charts_container = QFrame()
        charts_container.setFrameStyle(QFrame.Box)
        charts_container.setMinimumHeight(300)
        charts_layout = QGridLayout(charts_container)
        
        # Placeholder para gráficas
        chart1 = self.create_chart_placeholder("Ingresos por Mes")
        chart2 = self.create_chart_placeholder("Ocupación por Clase")
        chart3 = self.create_chart_placeholder("Nuevos Socios")
        chart4 = self.create_chart_placeholder("Tipos de Membresía")
        
        charts_layout.addWidget(chart1, 0, 0)
        charts_layout.addWidget(chart2, 0, 1)
        charts_layout.addWidget(chart3, 1, 0)
        charts_layout.addWidget(chart4, 1, 1)
        
        layout.addWidget(charts_container)
        
        # Espaciador
        layout.addStretch()
    
    def create_metric_card(self, title: str, value: str, icon: str, color: str) -> QFrame:
        """Crea una tarjeta de métrica."""
        card = QFrame()
        card.setFrameStyle(QFrame.Box)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border: 2px solid {color};
                border-radius: 10px;
                padding: 15px;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        
        # Icono y título
        header_layout = QHBoxLayout()
        
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 24px; color: {color};")
        header_layout.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        card_layout.addLayout(header_layout)
        
        # Valor
        value_label = QLabel(value)
        value_label.setObjectName(f"{title}_value")  # Para actualizar después
        value_font = QFont("Arial", 24, QFont.Bold)
        value_label.setFont(value_font)
        value_label.setStyleSheet(f"color: {color};")
        card_layout.addWidget(value_label)
        
        # Tendencia (placeholder)
        trend_label = QLabel("↑ +10% vs mes anterior")
        trend_label.setStyleSheet("color: #27ae60; font-size: 10px;")
        card_layout.addWidget(trend_label)
        
        return card
    
    def create_chart_placeholder(self, title: str) -> QFrame:
        """Crea un placeholder para gráfica."""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Box)
        frame.setStyleSheet("""
            QFrame {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
            }
        """)
        
        layout = QVBoxLayout(frame)
        
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont("Arial", 12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Placeholder
        placeholder = QLabel("📊 Gráfica aquí")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #95a5a6; font-size: 48px;")
        layout.addWidget(placeholder)
        
        return frame
    
    def load_metrics(self):
        """Carga las métricas del dashboard."""
        logger.info("Loading dashboard metrics")
        
        # Datos mock (en producción vendría del backend)
        metrics = {
            'total_members': "243",
            'active_members': "187",
            'monthly_income': "$45,320",
            'today_reservations': "42",
            'avg_occupancy': "78%",
            'new_members': "12"
        }
        
        # Actualizar valores en las tarjetas
        for key, value in metrics.items():
            if key in self.metric_cards:
                card = self.metric_cards[key]
                value_label = card.findChild(QLabel, f"{self.get_metric_title(key)}_value")
                if value_label:
                    value_label.setText(value)
        
        self.refresh_requested.emit()
    
    def get_metric_title(self, key: str) -> str:
        """Obtiene el título de una métrica por su key."""
        titles = {
            'total_members': "Socios Totales",
            'active_members': "Socios Activos",
            'monthly_income': "Ingresos del Mes",
            'today_reservations': "Reservas Hoy",
            'avg_occupancy': "Ocupación Promedio",
            'new_members': "Nuevos Socios"
        }
        return titles.get(key, key)
    
    def on_period_changed(self, period: str):
        """Maneja el cambio de período."""
        logger.info(f"Period changed to: {period}")
        self.load_metrics()
