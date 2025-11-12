# mood_sync_dashboard_with_stk.py
import os
import json
import time
import hashlib
import base64
import datetime
import requests

import pandas as pd
import numpy as np
from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objects as go
import plotly.express as px

# ----------------------------
# Setup & constants
# ----------------------------
np.random.seed(42)

counties = [
    "Nairobi","Mombasa","Kisumu","Nakuru","Eldoret","Thika","Malindi","Meru","Machakos","Kakamega",
    "Nyeri","Murang'a","Embu","Kericho","Bomet","Narok","Baringo","Laikipia","Bungoma",
    "Busia","Siaya","Homa Bay","Migori","Kisii","Nyamira","Garissa","Wajir","Mandera","Marsabit",
    "Isiolo","Kitui","Makueni","Taita Taveta","Kilifi","Kwale","Tana River","Samburu","Turkana",
    "West Pokot","Elgeyo Marakwet","Trans Nzoia","Nandi","Vihiga","Tharaka Nithi","Lamu","Kajiado","Kiambu"
]

payment_types = ['Mpesa','Airtel Money','Bank Transfer']
sectors = ['Transport','Communication','Retail','Banking','Government','Utilities']

app = Dash(__name__)
app.title = "MoodSync Kenya Dashboard - Live M-Pesa"

alert_log = []

USERS_FILE = "users.json"

# ----------------------------
# Safaricom Sandbox credentials (official test credentials you accepted)
# ----------------------------
MPESA_BASE_URL = "https://sandbox.safaricom.co.ke"
CONSUMER_KEY = "bwrYETJX1vaWbOXFTrf7A55oTgfC9YQNq1zoe6bScn6pnkmI"
CONSUMER_SECRET = "y1Njn0Aiq18khzQ5eGJneSG1Ju5dXICMv6ZXGatzEiymyhcGFfdCy1B0ode3MYCS"
SHORTCODE = "174379"  # sandbox test shortcode
PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"  # sandbox passkey

# IMPORTANT: Callback URL must be publicly reachable if you want to receive callbacks from Safaricom.
# For testing with ngrok, paste your ngrok URL here (e.g. "https://abcd1234.ngrok.io/mpesa_callback")
# For now it's a placeholder; replace before running STK-push if you need callbacks.
CALLBACK_URL = "https://your-public-callback-url.example.com/mpesa_callback"

# ----------------------------
# Helpers: users file read/write
# ----------------------------
def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def email_exists(email):
    users = load_users()
    for u in users:
        if u.get("email", "").lower() == (email or "").lower():
            return True
    return False

def add_user(full_name, email, password, subscription):
    users = load_users()
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    user = {
        "full_name": full_name,
        "email": email,
        "password_hash": hash_password(password),
        "subscription": subscription,
        "registered_at": timestamp
    }
    users.append(user)
    save_users(users)

# ----------------------------
# M-Pesa STK Push (Sandbox)
# ----------------------------
def get_mpesa_oauth_token():
    """
    Retrieves OAuth token from the sandbox.
    """
    url = f"{MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    auth_str = f"{CONSUMER_KEY}:{CONSUMER_SECRET}"
    b64 = base64.b64encode(auth_str.encode()).decode()
    headers = {"Authorization": f"Basic {b64}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("access_token")
    except Exception as e:
        # Return None on failure
        return None

def lipa_na_mpesa_stk_push(phone_number, amount, account_reference="Donation", transaction_desc="Donation"):
    """
    Initiates STK push via Safaricom sandbox.
    phone_number should be in format 2547XXXXXXXX (no +).
    amount is integer (KES).
    Returns dict with the API response or error info.
    """
    token = get_mpesa_oauth_token()
    if not token:
        return {"success": False, "error": "Failed to obtain MPESA OAuth token."}

    # Timestamp and password
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password_str = SHORTCODE + PASSKEY + timestamp
    password = base64.b64encode(password_str.encode()).decode()

    url = f"{MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "BusinessShortCode": SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": CALLBACK_URL,
        "AccountReference": account_reference,
        "TransactionDesc": transaction_desc
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        return {"success": True, "response": resp.json()}
    except requests.HTTPError as he:
        try:
            return {"success": False, "error": resp.json()}
        except Exception:
            return {"success": False, "error": str(he)}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ----------------------------
# Styles & App layout (original preserved)
# ----------------------------
CARD_STYLE = {'backgroundColor':'#161b22','borderRadius':'12px','padding':'15px',
              'marginBottom':'10px','boxShadow':'0 0 10px #58a6ff'}
APP_STYLE = {'backgroundColor':'#0d1117','color':'#fff','fontFamily':'Segoe UI, sans-serif','padding':'20px'}

app.layout = html.Div([
    dcc.Store(id='registered-user', data={'email': None, 'name': None}),
    
    # Navbar (horizontal, blue) - unchanged
    html.Div([
        dcc.Link("Dashboard", href="/", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
        dcc.Link("Registration", href="/register", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
        dcc.Link("AI Section", href="/ai", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
        dcc.Link("Donation", href="/donation", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
        dcc.Link("Partnership", href="/partnership", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    ], style={'backgroundColor':'#1f6feb','display':'flex','justifyContent':'center','alignItems':'center','gap':'8px','marginBottom':'18px','borderRadius':'6px'}),
    
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
], style=APP_STYLE)

# ----------------------------
# Dashboard layout (preserved)
# ----------------------------
def dashboard_layout():
    return html.Div([
        html.Div([
            html.Label("Select County:", style={'color':'#58a6ff','fontWeight':'bold'}),
            dcc.Dropdown(
                id='region-dropdown',
                options=[{'label':c,'value':c} for c in counties],
                value='Nairobi',
                clearable=False,
                style={'backgroundColor':'#21262d','color':'#ffffff','border':'1px solid #58a6ff',
                       'borderRadius':'6px','fontWeight':'bold','width':'50%','margin':'0 auto','boxShadow':'0 0 8px #58a6ff'}
            )
        ], style={'width':'50%', 'margin':'0 auto','marginBottom':'20px'}),

        html.Div([
            html.Div(id='total-txn', style={**CARD_STYLE,'display':'inline-block','width':'23%','color':'#58ff6f','textAlign':'center'}),
            html.Div(id='total-amt', style={**CARD_STYLE,'display':'inline-block','width':'23%','color':'#ff6f58','textAlign':'center'}),
            html.Div(id='current-tpm', style={**CARD_STYLE,'display':'inline-block','width':'23%','color':'#ff58ff','textAlign':'center'}),
            html.Div(id='trend-alert', style={**CARD_STYLE,'display':'inline-block','width':'23%','color':'#ffd658','textAlign':'center'})
        ], style={'textAlign':'center','marginBottom':'20px'}),

        html.Div([
            html.Div([
                dcc.Graph(id='tpm-chart', style={'height':'300px'}),
                dcc.Graph(id='payment-chart', style={'height':'450px'}),
                dcc.Graph(id='sector-chart', style={'height':'400px'}),
                dcc.Graph(id='top-counties-chart', style={'height':'400px'}),
                dcc.Graph(id='top-sectors-chart', style={'height':'350px'}),
                dcc.Graph(id='peak-hour-heatmap', style={'height':'300px'})
            ], style={'width':'70%','display':'inline-block','paddingRight':'20px'}),

            html.Div([
                html.H3("💬 AI Assistant", style={'color':'#58a6ff'}),
                dcc.Textarea(id='user-question', placeholder='Ask about averages, totals, or current TPM...',
                             style={'width':'100%','height':100,'backgroundColor':'#0d1117','color':'white','marginBottom':'10px'}),
                html.Button("Ask", id='ask-btn', n_clicks=0, style={'width':'100%','padding':'10px','backgroundColor':'#1f6feb','color':'white','border':'none','borderRadius':'8px'}),
                html.Div(id='ai-answer', style={**CARD_STYLE,'backgroundColor':'#21262d','marginTop':'10px'}),
                html.H3("⚠️ Recent Alerts", style={'color':'#d9534f','marginTop':'20px'}),
                html.Div(id='alert-log', style={
                    'backgroundColor':'#21262d',
                    'color':'#ffffff',
                    'height':'200px',
                    'overflowY':'scroll',
                    'padding':'10px',
                    'borderRadius':'6px',
                    'boxShadow':'0 0 10px #ff6f58'
                })
            ], style={'width':'28%','display':'inline-block','verticalAlign':'top'})
        ]),

        dcc.Interval(id='interval-update', interval=5000, n_intervals=0)
    ])

# ----------------------------
# Registration layout (stores to users.json)
# ----------------------------
def registration_layout():
    return html.Div([
        html.H2("User Registration", style={'color':'#1f6feb'}),
        html.Div([
            html.Div([html.Label("Full Name")]),
            dcc.Input(id='reg-name', type='text', placeholder='Full Name', style={'width':'50%','marginBottom':'8px'}),
            html.Div([html.Label("Email")]),
            dcc.Input(id='reg-email', type='email', placeholder='Email', style={'width':'50%','marginBottom':'8px'}),
            html.Div([html.Label("Password")]),
            dcc.Input(id='reg-password', type='password', placeholder='Password', style={'width':'50%','marginBottom':'8px'}),
            html.Div([html.Label("Subscription")]),
            dcc.RadioItems(id='reg-subscription', options=[
                {'label':'5/month','value':'5/month'},
                {'label':'50/lifetime','value':'50/lifetime'}
            ], style={'marginBottom':'10px'}),
            html.Button("Register", id='register-btn', n_clicks=0, style={'backgroundColor':'#1f6feb','color':'white','padding':'10px','border':'none','borderRadius':'8px'}),
            html.Div(id='register-message', style={'marginTop':'10px'})
        ], style={'maxWidth':'800px'})
    ])

# ----------------------------
# AI layout
# ----------------------------
def ai_layout(registered):
    if not registered:
        return html.Div([
            html.H3("AI Section - Login Required", style={'color':'#ff6f58'}),
            html.P("You must register or login to access the AI Assistant."),
            dcc.Link("Go to Registration", href="/register", style={'color':'#1f6feb','fontWeight':'600'})
        ])
    else:
        return html.Div([
            html.H2("AI — Convert thought into working ideas", style={'color':'#58a6ff'}),
            dcc.Textarea(id='user-question-ai-only', placeholder='Describe your thought or idea...',
                         style={'width':'60%','height':150,'backgroundColor':'#0d1117','color':'white','marginBottom':'10px'}),
            html.Button("Convert", id='ai-only-convert', n_clicks=0, style={'backgroundColor':'#1f6feb','color':'white','padding':'10px','border':'none','borderRadius':'8px'}),
            html.Div(id='ai-only-answer', style={**CARD_STYLE,'backgroundColor':'#21262d','marginTop':'10px','maxWidth':'800px'})
        ])

# ----------------------------
# Donation layout (STK push, available to all)
# ----------------------------
def donation_layout():
    return html.Div([
        html.H2("Donation (M-Pesa STK Push - Sandbox)", style={'color':'#1f6feb'}),
        html.P("Enter phone number in format 2547XXXXXXXX and amount (KES). This uses Safaricom sandbox credentials."),
        html.Div([
            html.Label("Phone Number (2547XXXXXXXX)"), dcc.Input(id='donate-phone', type='text', placeholder='2547XXXXXXXX', style={'width':'40%'}),
            html.Br(), html.Br(),
            html.Label("Amount (KES)"), dcc.Input(id='donate-amount', type='number', placeholder='100', style={'width':'20%'}),
            html.Br(), html.Br(),
            html.Button("Donate (STK Push)", id='donate-btn', n_clicks=0, style={'backgroundColor':'#1f6feb','color':'white','padding':'10px','border':'none','borderRadius':'8px'}),
            html.Div(id='donation-message', style={'marginTop':'12px','maxWidth':'700px','wordBreak':'break-word'})
        ], style={'maxWidth':'900px'})
    ])

# ----------------------------
# Partnership layout (unchanged)
# ----------------------------
def partnership_layout():
    return html.Div([
        html.H2("Partnership", style={'color':'#1f6feb'}),
        html.P("This dashboard allows monitoring of M-Pesa transactions across Kenya. It shows TPM, payment-type trends, sector trends, top counties and alerts."),
        html.P("Contact: denisgitari082@gmail.com"),
        html.H4("Describe Yourself (we'll send this to the partnership inbox)"),
        dcc.Textarea(id='partner-desc', placeholder='Write something about yourself...', style={'width':'60%','height':150}),
        html.Br(), html.Br(),
        html.Button("Send", id='partner-send', n_clicks=0, style={'backgroundColor':'#1f6feb','color':'white','padding':'10px','border':'none','borderRadius':'8px'}),
        html.Div(id='partner-msg', style={'marginTop':'10px','maxWidth':'800px'})
    ])

# ----------------------------
# Page router
# ----------------------------
@app.callback(Output('page-content','children'),
              Input('url','pathname'),
              State('registered-user','data'))
def display_page(pathname, user_data):
    registered = user_data.get('email') is not None
    if pathname == '/register':
        return registration_layout()
    elif pathname == '/ai':
        return ai_layout(registered)
    elif pathname == '/donation':
        return donation_layout()
    elif pathname == '/partnership':
        return partnership_layout()
    else:
        return dashboard_layout()

# ----------------------------
# Registration callback (now writes to users.json)
# ----------------------------
@app.callback(
    Output('register-message','children'),
    Output('registered-user','data'),
    Input('register-btn','n_clicks'),
    State('reg-name','value'),
    State('reg-email','value'),
    State('reg-password','value'),
    State('reg-subscription','value'),
    State('registered-user','data')
)
def register_user(n, name, email, password, subscription, stored):
    if n and n > 0:
        # basic validation
        if not all([name, email, password, subscription]):
            return "All fields are required.", stored
        # check duplicate
        if email_exists(email):
            return "An account with that email already exists.", stored
        # add user
        try:
            add_user(name, email, password, subscription)
            stored['email'] = email
            stored['name'] = name
            return f"Registration successful! Welcome {name}.", stored
        except Exception as e:
            return f"Failed to register: {str(e)}", stored
    return "", stored

# ----------------------------
# Donation callback - performs STK push (sandbox)
# ----------------------------
@app.callback(
    Output('donation-message','children'),
    Input('donate-btn','n_clicks'),
    State('donate-phone','value'),
    State('donate-amount','value')
)
def perform_donation(n, phone, amount):
    if not n or n == 0:
        return ""
    if not phone or not amount:
        return "Please provide phone number and amount."
    phone_str = str(phone).strip()
    # basic validation for Kenyan mobile format
    if not (phone_str.startswith("254") and len(phone_str) >= 12):
        return "Phone number must be in format 2547XXXXXXXX."
    try:
        amount_int = int(amount)
        if amount_int <= 0:
            return "Amount must be a positive number."
    except Exception:
        return "Invalid amount."

    # Initiate STK push
    res = lipa_na_mpesa_stk_push(phone_str, amount_int, account_reference="Donation", transaction_desc="Donation")
    if not res.get("success"):
        return html.Div([
            html.Div("Failed to send STK push (sandbox)."),
            html.Pre(str(res.get("error")))
        ])
    # Success - show message and raw response for debugging
    resp = res.get("response", {})
    return html.Div([
        html.Div("STK Push request sent (sandbox). Check your phone for prompt."),
        html.Pre(json.dumps(resp, indent=2))
    ])

# ----------------------------
# Partnership callback (unchanged simulated send)
# ----------------------------
@app.callback(
    Output('partner-msg','children'),
    Input('partner-send','n_clicks'),
    State('partner-desc','value')
)
def send_partner(n, desc):
    if n and n > 0:
        if desc and desc.strip():
            # simulate sending an email to denisgitari082@gmail.com
            return "Your description has been sent to the partnership inbox (simulated). Thank you!"
        return "Please describe yourself before sending."
    return ""

# ----------------------------
# Process transactions and original dashboard callbacks (preserved)
# ----------------------------
def process_transactions(transactions, county):
    if not transactions:
        minutes = pd.date_range(end=datetime.datetime.now(), periods=60, freq='T')
        tpm = np.random.randint(200,1200, size=len(minutes))
        df_tpm = pd.DataFrame({'datetime': minutes, 'tpm': tpm})
    else:
        df = pd.DataFrame(transactions)
        df['datetime'] = pd.to_datetime(df['timestamp'])
        df_tpm = df.groupby(pd.Grouper(key='datetime', freq='T')).size().reset_index(name='tpm')

    payment_trend = pd.DataFrame({
        'datetime': df_tpm['datetime'],
        'Mpesa': df_tpm['tpm']*0.7,
        'Airtel Money': df_tpm['tpm']*0.2,
        'Bank Transfer': df_tpm['tpm']*0.1
    }).melt(id_vars='datetime', var_name='Payment Type', value_name='Transactions')

    sector_trend = []
    for _, row in df_tpm.iterrows():
        dist = np.random.dirichlet(np.ones(len(sectors)))*row['tpm']
        entry = dict(zip(sectors, dist))
        entry['datetime'] = row['datetime']
        sector_trend.append(entry)
    sector_trend = pd.DataFrame(sector_trend).melt(id_vars='datetime', value_vars=sectors, var_name='Sector', value_name='Transactions')

    df_tpm['hour'] = df_tpm['datetime'].dt.hour
    heatmap = df_tpm.groupby('hour')['tpm'].sum().reset_index()

    top_counties = pd.DataFrame({
        'County': counties,
        'Transactions': np.random.randint(1000,5000,len(counties))
    }).sort_values('Transactions', ascending=False).head(5)

    return df_tpm, payment_trend, sector_trend, heatmap, top_counties

@app.callback(
    [Output('tpm-chart','figure'),
     Output('payment-chart','figure'),
     Output('sector-chart','figure'),
     Output('top-counties-chart','figure'),
     Output('top-sectors-chart','figure'),
     Output('peak-hour-heatmap','figure'),
     Output('total-txn','children'),
     Output('total-amt','children'),
     Output('current-tpm','children'),
     Output('trend-alert','children'),
     Output('alert-log','children')],
    [Input('region-dropdown','value'),
     Input('interval-update','n_intervals')]
)
def update_dashboard(county, n):
    global alert_log
    try:
        token = get_mpesa_oauth_token()
        # In case you later implement a real endpoint, adapt get_recent_transactions to use token
        transactions = []  # keep using simulated - original behavior preserved
    except Exception:
        transactions = []

    df_tpm, payment_trend, sector_trend, heatmap, top_counties = process_transactions(transactions, county)

    tpm_fig = px.line(df_tpm, x='datetime', y='tpm', title=f"{county} - Transactions per Minute", template='plotly_dark')
    payment_fig = px.line(payment_trend, x='datetime', y='Transactions', color='Payment Type', template='plotly_dark', title=f"{county} Payment Type Trend")
    sector_fig = px.area(sector_trend, x='datetime', y='Transactions', color='Sector', template='plotly_dark', title=f"{county} Sector Trend")
    heat_fig = px.bar(heatmap, x='hour', y='tpm', title=f"{county} Peak Hour Heatmap", template='plotly_dark')
    top_counties_fig = px.bar(top_counties, x='County', y='Transactions', template='plotly_dark', title="Top Counties")
    top_sectors = sector_trend.groupby('Sector')['Transactions'].sum().sort_values(ascending=False).head(5).reset_index()
    top_sectors_fig = px.bar(top_sectors, x='Sector', y='Transactions', text='Transactions', template='plotly_dark', title=f"Top 5 Sectors in {county}")
    top_sectors_fig.update_traces(marker_color="#ff6f58", textposition="outside")

    total_txn_val = int(df_tpm['tpm'].sum())
    total_amt_val = int(total_txn_val * 150)
    current_tpm_val = int(df_tpm['tpm'].iloc[-1])

    avg_tpm = df_tpm['tpm'].rolling(10).mean().iloc[-1]
    last_tpm = df_tpm['tpm'].iloc[-1]
    diff = (last_tpm - avg_tpm) / avg_tpm * 100 if avg_tpm > 0 else 0
    alert = "🚀 Spike!" if diff > 50 else "📉 Drop!" if diff < -50 else "✅ Stable"
    if diff > 50 or diff < -50:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        alert_log.append(f"{timestamp} - {county}: {alert}")
    alert_log = alert_log[-5:]
    alert_log_display = html.Ul([html.Li(a) for a in alert_log])

    def sparkline(data, color):
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=data, mode='lines', line=dict(color=color, width=1)))
        fig.update_layout(template='plotly_dark', margin=dict(l=0,r=0,t=0,b=0), height=50,
                          xaxis=dict(visible=False), yaxis=dict(visible=False))
        return dcc.Graph(figure=fig, style={'height':'50px'})

    return (tpm_fig, payment_fig, sector_fig, top_counties_fig, top_sectors_fig, heat_fig,
            html.Div([f"Total Txns (Last Hour): {total_txn_val:,}", sparkline(df_tpm['tpm'], '#58ff6f')]),
            html.Div([f"Total Amount (KES): {total_amt_val:,}", sparkline(df_tpm['tpm'] * 150, '#ff6f58')]),
            html.Div([f"Current TPM: {current_tpm_val:,}", sparkline(df_tpm['tpm'], '#ff58ff')]),
            html.Div([alert, sparkline(df_tpm['tpm'], '#ffd658')]),
            alert_log_display)

# ----------------------------
# AI assistant callbacks (preserved + ai-only converter)
# ----------------------------
@app.callback(
    Output('ai-answer','children'),
    [Input('ask-btn','n_clicks')],
    [State('user-question','value'),
     State('region-dropdown','value')]
)
def ai_assistant_on_dashboard(n, q, county):
    if not n or not q:
        return ""
    avg_tpm = np.random.randint(500,3000)
    total_amount = np.random.randint(1_000_000,20_000_000)
    last_tpm = np.random.randint(500,3000)
    ql = q.lower()
    if 'average' in ql:
        return f"Average transactions per minute in {county}: {avg_tpm:,}."
    if 'total' in ql:
        return f"Total amount processed in {county} today: KES {total_amount:,}."
    if 'current' in ql or 'latest' in ql:
        return f"Current transactions per minute in {county}: {last_tpm:,}."
    return "Try asking about average, total, or current transactions."

@app.callback(
    Output('ai-only-answer','children'),
    Input('ai-only-convert','n_clicks'),
    State('user-question-ai-only','value'),
    State('registered-user','data')
)
def ai_only_convert(n, text, user_data):
    if not n or not text:
        return ""
    if not user_data or not user_data.get('email'):
        return "Please register to use this feature."
    lines = []
    lines.append(html.H4("Converted idea — quick starter", style={'marginTop':'0'}))
    lines.append(html.Ul([
        html.Li("One-sentence summary: " + (text[:120] + ("..." if len(text) > 120 else ""))),
        html.Li("Possible product/service: " + ("A web app / marketplace / API" )),
        html.Li("First MVP feature: " + "User registration + core functionality"),
        html.Li("Suggested tech stack: " + "Python (Dash/Flask), PostgreSQL, React (optional)"),
        html.Li("Next steps: " + "Build simple prototype, test with 5 users, iterate")
    ]))
    return html.Div(lines, style={'padding':'8px'})

# ----------------------------
# Run app
# ----------------------------
if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=8080)


