import streamlit as st
import mysql.connector
from mysql.connector import Error
import os
import sys
import time
from dotenv import load_dotenv
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

root_dir = os.path.join(os.path.dirname(__file__), '..')
env_path = os.path.join(root_dir, '.env')
load_dotenv(env_path)

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

st.set_page_config(
    page_title="AtlasGrid",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .main-title {
        text-align: center;
        color: #1f77b4;
        font-size: 3em;
        font-weight: bold;
        margin-bottom: 10px;
    }
    
    .parking-card {
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        font-size: 1.2em;
        margin: 5px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .available {
        background-color: #28a745;
        color: white;
    }
    
    .occupied {
        background-color: #dc3545;
        color: white;
    }
    
    .obstacle {
        background-color: #ff8c00;
        color: white;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 2.5em;
    }
    
    .section-header {
        font-size: 1.8em;
        font-weight: bold;
        margin-top: 30px;
        margin-bottom: 15px;
        color: #333;
    }
</style>
""", unsafe_allow_html=True)


def get_peak_hours_data(start_date, end_date):
    """
    Query the database to get hourly occupancy data for a specified date range.
    Filters to business hours only (7 AM - 10 PM).
    """
    try:
        missing_configs = [k for k, v in DB_CONFIG.items() if not v]
        if missing_configs:
            return None, None, f"Configuración de base de datos faltante: {', '.join(missing_configs)}."
        
        connection = mysql.connector.connect(**DB_CONFIG)
        
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            
            days_in_range = (end_date - start_date).days + 1
            if days_in_range < 1:
                days_in_range = 1
            
            query = """
                SELECT 
                    HOUR(TimeOfEntry) as hour,
                    COUNT(*) as occupancy_count
                FROM occupancyhistory
                WHERE TimeOfEntry >= %s 
                    AND TimeOfEntry < %s
                    AND CheckIfObjectIsCar = TRUE
                    AND HOUR(TimeOfEntry) BETWEEN 7 AND 22
                GROUP BY HOUR(TimeOfEntry)
                ORDER BY hour
            """
            cursor.execute(query, (start_date, end_date + timedelta(days=1)))
            results = cursor.fetchall()
            
            cursor.close()
            connection.close()
            
            hours = list(range(7, 23))
            occupancy_counts = [0] * len(hours)
            
            for row in results:
                hour = row['hour']
                count = row['occupancy_count']
                hour_index = hour - 7  # Convert to index (0-15)
                if 0 <= hour_index < len(hours):
                    occupancy_counts[hour_index] = count / days_in_range
            
            return hours, occupancy_counts, None
    
    except Error as error:
        return None, None, f"Error de conexión a la base de datos: {str(error)}"


def get_parking_data():
    """
    Query the database to get current parking space status.
    Returns a dictionary with parking space data and metrics.
    """
    try:
        missing_configs = [k for k, v in DB_CONFIG.items() if not v]
        if missing_configs:
            return {
                'spaces': [],
                'metrics': {
                    'total': 0,
                    'available': 0,
                    'occupied': 0,
                    'obstacles': 0,
                    'occupancy_rate': 0
                },
                'error': f"Configuración de base de datos faltante: {', '.join(missing_configs)}."
            }
        
        connection = mysql.connector.connect(**DB_CONFIG)
        
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            
            query = """
                SELECT ParkingSpaceID, SpaceCode, Status 
                FROM parkingspace 
                ORDER BY SpaceCode
            """
            cursor.execute(query)
            spaces = cursor.fetchall()
            
            total_spaces = len(spaces)
            available = sum(1 for s in spaces if s['Status'] == 'available')
            occupied = sum(1 for s in spaces if s['Status'] == 'occupied')
            obstacles = sum(1 for s in spaces if s['Status'] == 'obstacle')
            
            occupancy_rate = (occupied / total_spaces * 100) if total_spaces > 0 else 0
            
            cursor.close()
            connection.close()
            
            return {
                'spaces': spaces,
                'metrics': {
                    'total': total_spaces,
                    'available': available,
                    'occupied': occupied,
                    'obstacles': obstacles,
                    'occupancy_rate': occupancy_rate
                },
                'error': None
            }
    
    except Error as error:
        return {
            'spaces': [],
            'metrics': {
                'total': 0,
                'available': 0,
                'occupied': 0,
                'obstacles': 0,
                'occupancy_rate': 0
            },
            'error': f"Error de conexión a la base de datos: {str(error)}"
        }


def display_parking_space_card(space_code, status):
    """
    Display a single parking space as a colored card.
    """
    status_info = {
        'available': ('Disponible', 'available', '✅'),
        'occupied': ('Ocupado', 'occupied', '🚗'),
        'obstacle': ('Obstáculo', 'obstacle', '⚠️')
    }
    
    display_text, css_class, icon = status_info.get(status, ('Desconocido', 'available', '❓'))
    
    st.markdown(f"""
        <div class="parking-card {css_class}">
            <div style="font-size: 2em;">{icon}</div>
            <div style="font-size: 1.5em; margin: 10px 0;">{space_code}</div>
            <div>{display_text}</div>
        </div>
    """, unsafe_allow_html=True)


def generate_peak_hours_chart(start_date, end_date, period_name="Esta Semana"):
    """
    Generate a matplotlib bar chart showing peak hours based on historical data.
    Only shows business hours (7 AM - 10 PM).
    """
    hours, occupancy_counts, error = get_peak_hours_data(start_date, end_date)
    
    if error:
        return None, error
    
    if hours is None or occupancy_counts is None:
        return None, "No hay datos disponibles para mostrar."
    
    fig, ax = plt.subplots(figsize=(12, 5))
    
    # Create bar chart
    bars = ax.bar(hours, occupancy_counts, color='#1f77b4', alpha=0.8, edgecolor='#155a8a', linewidth=1.5, label='Horas Normales')
    
    # Highlight peak hours (top 3)
    if occupancy_counts and max(occupancy_counts) > 0:
        sorted_indices = sorted(range(len(occupancy_counts)), key=lambda i: occupancy_counts[i], reverse=True)
        peak_hours_shown = []
        for i in sorted_indices[:3]:
            if occupancy_counts[i] > 0:  # Only highlight if there's actual data
                bars[i].set_color('#dc3545')
                bars[i].set_alpha(0.9)
                peak_hours_shown.append(i)
        
        # Add legend
        if peak_hours_shown:
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor='#1f77b4', edgecolor='#155a8a', alpha=0.8, label='Horas Normales'),
                Patch(facecolor='#dc3545', alpha=0.9, label='Top 3 Horas Pico')
            ]
            ax.legend(handles=legend_elements, loc='upper right', framealpha=0.9)
    
    ax.set_xlabel('Hora del Día', fontsize=12, fontweight='bold')
    ax.set_ylabel('Promedio de Espacios Ocupados', fontsize=12, fontweight='bold')
    ax.set_title(f'Horas Pico de Ocupación - {period_name} (Horario: 7:00 AM - 10:00 PM)', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(hours)
    ax.set_xticklabels([f'{h:02d}:00' for h in hours], rotation=45, ha='right')
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_ylim(bottom=0)
    
    for i, (hour, count) in enumerate(zip(hours, occupancy_counts)):
        if count > 0:
            ax.text(hour, count, f'{count:.1f}', ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    
    return fig, None


def main():
    st.markdown('<h1 class="main-title">¡Bienvenido a Plaza Iglesias!</h1>', unsafe_allow_html=True)
    st.markdown("---")
    
    data = get_parking_data()
    
    if data['error']:
        st.error(f"Error de Conexión a la Base de Datos: {data['error']}")
        return
    
    metrics = data['metrics']
    spaces = data['spaces']
    
    st.markdown('<div class="section-header"> Estado en Tiempo Real</div>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="🟢 Espacios Disponibles",
            value=metrics['available'],
            delta=None
        )
    
    with col2:
        st.metric(
            label="🔴 Espacios Ocupados",
            value=metrics['occupied'],
            delta=None
        )
    
    with col3:
        st.metric(
            label="⚠️ Obstáculos Detectados",
            value=metrics['obstacles'],
            delta=None
        )
    
    with col4:
        st.metric(
            label="📈 Tasa de Ocupación",
            value=f"{metrics['occupancy_rate']:.1f}%",
            delta=None
        )
    
    st.markdown("---")
    
    st.markdown('<div class="section-header">🅿️ Espacios de Estacionamiento</div>', unsafe_allow_html=True)
    
    if spaces:
        cols_per_row = 4
        for row_idx, i in enumerate(range(0, len(spaces), cols_per_row)):
            cols = st.columns(cols_per_row)
            row_spaces = spaces[i:i+cols_per_row]
            # Reverse the second row (row_idx == 1)
            if row_idx == 1:
                row_spaces = list(reversed(row_spaces))
            
            for j, col in enumerate(cols):
                if j < len(row_spaces):
                    space = row_spaces[j]
                    with col:
                        display_parking_space_card(space['SpaceCode'], space['Status'])
    else:
        st.warning("No se encontraron espacios de estacionamiento en la base de datos.")
    
    st.markdown("---")
    
    # Peak Hours Chart
    st.markdown('<div class="section-header">📊 Análisis de Horas Pico</div>', unsafe_allow_html=True)
    
    # Filter controls
    col_filter1, col_filter2, col_filter3 = st.columns([2, 2, 2])
    
    with col_filter1:
        time_period = st.selectbox(
            "Período de Tiempo",
            ["Hoy", "Esta Semana", "Este Mes", "Rango Personalizado"],
            key="time_period_selector"
        )
    
    start_date = None
    end_date = None
    period_name = time_period
    
    # Calculate dates based on selection
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    if time_period == "Hoy":
        start_date = today
        end_date = today
        period_name = "Hoy"
    elif time_period == "Esta Semana":
        start_date = today - timedelta(days=6)
        end_date = today
        period_name = "Últimos 7 Días"
    elif time_period == "Este Mes":
        start_date = today.replace(day=1)
        end_date = today
        period_name = "Este Mes"
    elif time_period == "Rango Personalizado":
        with col_filter2:
            custom_start = st.date_input(
                "Fecha Inicio",
                value=today - timedelta(days=7),
                max_value=today,
                key="custom_start_date"
            )
        with col_filter3:
            custom_end = st.date_input(
                "Fecha Fin",
                value=today,
                max_value=today,
                key="custom_end_date"
            )
        
        start_date = datetime.combine(custom_start, datetime.min.time())
        end_date = datetime.combine(custom_end, datetime.min.time())
        
        if start_date > end_date:
            st.warning("La fecha de inicio debe ser anterior a la fecha de fin.")
            start_date, end_date = end_date, start_date
        
        period_name = f"{custom_start.strftime('%d/%m/%Y')} - {custom_end.strftime('%d/%m/%Y')}"
    
    st.markdown(
        f"<div style='text-align: center; color: #666; font-size: 0.95em; margin: 10px 0;'>"
        f"Mostrando datos desde {start_date.strftime('%d/%m/%Y')} hasta {end_date.strftime('%d/%m/%Y')}"
        f"</div>", 
        unsafe_allow_html=True
    )
    
    fig, chart_error = generate_peak_hours_chart(start_date, end_date, period_name)
    
    if chart_error:
        st.warning(f"No se pudo generar el gráfico de horas pico: {chart_error}")
    elif fig:
        st.pyplot(fig)
        plt.close(fig)
        st.markdown(
            "<div style='text-align: center; color: #666; font-size: 0.9em;'>"
            "Horario de negocio: 7:00 AM - 10:00 PM. Las barras rojas indican las 3 horas con mayor ocupación promedio."
            "</div>", 
            unsafe_allow_html=True
        )
    else:
        st.info("No hay suficientes datos históricos para generar el gráfico.")
    
    st.markdown("---")
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f"<div style='text-align: center; color: #666;'>Última actualización: {current_time}</div>", unsafe_allow_html=True)
    
    time.sleep(1)
    st.rerun()


if __name__ == "__main__":
    main()