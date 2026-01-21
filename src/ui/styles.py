"""Global UI styles and theme configuration for UBA (Unbeaten Area)."""
import textwrap

# App Branding
APP_NAME_CN = "不败之地"
APP_NAME_EN = "UBA"
APP_FULL_NAME = "Unbeaten Area"
APP_SLOGAN = "估值触发投资系统 | Value Investing Made Simple"

# Color Palette
COLORS = {
    "primary": "#1E88E5",      # Blue
    "secondary": "#43A047",    # Green
    "accent": "#FF9800",       # Orange
    "danger": "#E53935",       # Red
    "warning": "#FFC107",      # Yellow
    "info": "#00ACC1",         # Cyan
    "dark": "#263238",         # Dark gray
    "light": "#ECEFF1",        # Light gray
    "success": "#4CAF50",      # Success green
    "buy": "#4CAF50",          # Buy signal - green
    "sell": "#F44336",         # Sell signal - red
    "hold": "#2196F3",         # Hold - blue
    "add": "#FF9800",          # Add position - orange
}

# Global CSS Styles
GLOBAL_CSS = """
<style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap');

    /* Global Styles */
    .stApp {
        font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Header Styles */
    .main-header {
        background: linear-gradient(135deg, #1E88E5 0%, #1565C0 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    .main-header h1 {
        color: white;
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
    }

    .main-header p {
        color: rgba(255, 255, 255, 0.9);
        margin: 0.5rem 0 0 0;
        font-size: 0.95rem;
    }

    /* Logo and Branding */
    .brand-container {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .brand-logo {
        font-size: 2.5rem;
    }

    .brand-text {
        display: flex;
        flex-direction: column;
    }

    .brand-name-cn {
        font-size: 1.8rem;
        font-weight: 700;
        color: white;
        line-height: 1.2;
    }

    .brand-name-en {
        font-size: 0.9rem;
        color: rgba(255, 255, 255, 0.85);
        letter-spacing: 2px;
    }

    /* Card Styles */
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 1.25rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        border: 1px solid #E0E0E0;
        transition: all 0.3s ease;
    }

    .metric-card:hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
        transform: translateY(-2px);
    }

    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1E88E5;
    }

    .metric-label {
        font-size: 0.9rem;
        color: #666;
        margin-top: 0.25rem;
    }

    /* Status Badge Styles */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 500;
    }

    .status-buy {
        background: rgba(76, 175, 80, 0.15);
        color: #2E7D32;
    }

    .status-sell {
        background: rgba(244, 67, 54, 0.15);
        color: #C62828;
    }

    .status-hold {
        background: rgba(33, 150, 243, 0.15);
        color: #1565C0;
    }

    .status-monitor {
        background: rgba(158, 158, 158, 0.15);
        color: #616161;
    }

    /* Alert Box Styles */
    .alert-box {
        padding: 1rem 1.25rem;
        border-radius: 8px;
        margin: 0.75rem 0;
        display: flex;
        align-items: flex-start;
        gap: 12px;
    }

    .alert-success {
        background: rgba(76, 175, 80, 0.1);
        border-left: 4px solid #4CAF50;
    }

    .alert-warning {
        background: rgba(255, 152, 0, 0.1);
        border-left: 4px solid #FF9800;
    }

    .alert-danger {
        background: rgba(244, 67, 54, 0.1);
        border-left: 4px solid #F44336;
    }

    .alert-info {
        background: rgba(33, 150, 243, 0.1);
        border-left: 4px solid #2196F3;
    }

    /* Table Styles */
    .dataframe {
        border-radius: 8px !important;
        overflow: hidden;
    }

    .dataframe thead tr th {
        background: #F5F5F5 !important;
        font-weight: 600 !important;
        color: #333 !important;
    }

    /* Button Styles */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.3s ease;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    }

    /* Section Header */
    .section-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin: 1.5rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #E0E0E0;
    }

    .section-header h3 {
        margin: 0;
        color: #333;
        font-weight: 600;
    }

    /* Stock Card */
    .stock-card {
        background: white;
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
        border: 1px solid #E0E0E0;
        transition: all 0.3s ease;
    }

    .stock-card:hover {
        border-color: #1E88E5;
        box-shadow: 0 4px 12px rgba(30, 136, 229, 0.15);
    }

    .stock-name {
        font-size: 1.1rem;
        font-weight: 600;
        color: #333;
    }

    .stock-code {
        font-size: 0.85rem;
        color: #666;
    }

    /* Price Display */
    .price-up {
        color: #E53935;
    }

    .price-down {
        color: #43A047;
    }

    .price-flat {
        color: #757575;
    }

    /* Footer */
    .app-footer {
        text-align: center;
        padding: 1.5rem;
        margin-top: 2rem;
        border-top: 1px solid #E0E0E0;
        color: #666;
        font-size: 0.85rem;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb {
        background: #c1c1c1;
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: #a1a1a1;
    }

    /* Sidebar styling */
    .css-1d391kg {
        background: linear-gradient(180deg, #1E88E5 0%, #1565C0 100%);
    }

    /* Expander styling */
    .streamlit-expanderHeader {
        font-weight: 600;
        color: #333;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 0.5rem 1rem;
    }
</style>
"""

# Page Configuration
def get_page_config(title: str, icon: str = "📊"):
    """Get standard page configuration."""
    return {
        "page_title": f"{title} - {APP_NAME_CN} | {APP_NAME_EN}",
        "page_icon": icon,
        "layout": "wide",
        "initial_sidebar_state": "expanded"
    }


def render_header(title: str, subtitle: str = None, icon: str = "📊"):
    """Render a styled page header."""
    subtitle_html = f'<p>{subtitle}</p>' if subtitle else ''
    return textwrap.dedent(f"""
    <div class="main-header">
        <div class="brand-container">
            <span class="brand-logo">{icon}</span>
            <div class="brand-text">
                <span class="brand-name-cn">{title}</span>
                <span class="brand-name-en">{APP_NAME_EN} • {APP_FULL_NAME}</span>
            </div>
        </div>
        {subtitle_html}
    </div>
    """)


def render_main_header():
    """Render the main app header with full branding."""
    return textwrap.dedent(f"""
    <div class="main-header">
        <div class="brand-container">
            <span class="brand-logo">🛡️</span>
            <div class="brand-text">
                <span class="brand-name-cn">{APP_NAME_CN}</span>
                <span class="brand-name-en">{APP_NAME_EN} • {APP_FULL_NAME}</span>
            </div>
        </div>
        <p>{APP_SLOGAN}</p>
    </div>
    """)


def render_metric_card(value: str, label: str, icon: str = "", delta: str = None):
    """Render a styled metric card."""
    delta_html = f'<div style="font-size: 0.85rem; color: {"#4CAF50" if delta and delta.startswith("+") else "#F44336"}">{delta}</div>' if delta else ''
    return f'<div class="metric-card"><div style="display: flex; align-items: center; gap: 8px;"><span style="font-size: 1.5rem;">{icon}</span><div><div class="metric-value">{value}</div><div class="metric-label">{label}</div>{delta_html}</div></div></div>'


def render_alert(message: str, type: str = "info", icon: str = None):
    """Render a styled alert box."""
    icons = {
        "success": "✅",
        "warning": "⚠️",
        "danger": "🚨",
        "info": "ℹ️"
    }
    icon = icon or icons.get(type, "ℹ️")
    return textwrap.dedent(f"""
    <div class="alert-box alert-{type}">
        <span style="font-size: 1.2rem;">{icon}</span>
        <div>{message}</div>
    </div>
    """)


def render_footer():
    """Render the app footer."""
    return textwrap.dedent(f"""
    <div class="app-footer">
        <p><strong>{APP_NAME_CN}</strong> ({APP_NAME_EN}) - {APP_FULL_NAME}</p>
        <p>价值投资 · 不败之地 | Value Investing Made Simple</p>
    </div>
    """)


def get_status_style(status: str) -> str:
    """Get CSS class for status badge."""
    status_map = {
        "buy": "status-buy",
        "sell": "status-sell",
        "hold": "status-hold",
        "monitor": "status-monitor",
        "triggered": "status-buy",
        "overvalued": "status-sell",
    }
    return status_map.get(status.lower(), "status-monitor")


def format_change(value: float) -> tuple:
    """Format price change with appropriate color class."""
    if value > 0:
        return f"+{value:.2f}%", "price-up"
    elif value < 0:
        return f"{value:.2f}%", "price-down"
    else:
        return "0.00%", "price-flat"
