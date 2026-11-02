import os
import json
import pandas as pd
import numpy as np
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler

# ==========================================
# 1. THE BACKEND (Data Loader & Scrubber)
# ==========================================
csv_filename = 'NIFTY BANK_minute.csv'
if not os.path.exists(csv_filename):
    for alt in ['BANKNIFTY_minute.csv', 'BankNifty_minute.csv', 'NIFTY 50_minute.csv']:
        if os.path.exists(alt):
            csv_filename = alt
            break

print(f"Loading 1-minute dataset from: {csv_filename}...")
df = pd.read_csv(csv_filename)

df.rename(columns=lambda x: x.strip().capitalize(), inplace=True)
if 'Datetime' in df.columns:
    df.rename(columns={'Datetime': 'Date'}, inplace=True)

df['Date'] = pd.to_datetime(df['Date'], utc=True)
df.sort_values('Date', inplace=True)
df.drop_duplicates(subset=['Date'], keep='last', inplace=True) 
df.dropna(subset=['Open', 'High', 'Low', 'Close'], inplace=True) 
df.reset_index(drop=True, inplace=True)

print("Preparing chart data...")
timestamps = df['Date'].values.astype('datetime64[s]').astype('int64')
opens = df['Open'].values
highs = df['High'].values
lows = df['Low'].values
closes = df['Close'].values

# ==========================================
# 2. JSON EXPORT (CLEAN STATE)
# ==========================================
lookback = 5000 
c_time = timestamps[-lookback:]
c_open = opens[-lookback:]
c_high = highs[-lookback:]
c_low = lows[-lookback:]
c_close = closes[-lookback:]
c_vol = df['Volume'].values[-lookback:] if 'Volume' in df.columns else np.zeros(min(lookback, len(df)))

kline_data = [{"time": int(c_time[idx]), "open": float(c_open[idx]), "high": float(c_high[idx]), "low": float(c_low[idx]), "close": float(c_close[idx]), "volume": float(c_vol[idx])} for idx in range(len(c_time))]

json_data = json.dumps(kline_data)
# Empty states by default
json_markers = "[]"
json_cycles = "[]"
json_trades = "[]"
json_stats = "{}"

# ==========================================
# 3. HTML GENERATION
# ==========================================
html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Pine Script Engine (Pro)</title>
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body { margin: 0; padding: 0; background: #131722; color: #d1d4dc; font-family: -apple-system, BlinkMacSystemFont, sans-serif; display: flex; flex-direction: column; overflow: hidden; height: 100vh; user-select: none; transition: background 0.3s; }
        body.light-theme { background: #ffffff; color: #131722; }
        
        #top-bar { height: 44px; background: #131722; border-bottom: 1px solid #2B2B43; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; z-index: 20; transition: background 0.3s, border-bottom 0.3s; flex-shrink: 0; }
        body.light-theme #top-bar { background: #ffffff; border-bottom: 1px solid #e0e3eb; }
        
        .tb-group { display: flex; align-items: center; gap: 8px; }
        .tb-btn { color: #d1d4dc; font-size: 14px; cursor: pointer; transition: 0.2s; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 4px 8px; border-radius: 4px; }
        body.light-theme .tb-btn { color: #131722; }
        .tb-btn:hover { background: #2B2B43; color: #fff; }
        body.light-theme .tb-btn:hover { background: #f0f3fa; color: #2962FF; }
        .tb-btn svg { width: 18px; height: 18px; stroke: currentColor; fill: none; stroke-width: 1.5; }
        .tb-text-bold { font-weight: 600; font-size: 15px; color: #fff; }
        body.light-theme .tb-text-bold { color: #131722; }
        .divider { width: 1px; height: 20px; background: #2B2B43; margin: 0 4px; transition: 0.3s; }
        body.light-theme .divider { background: #e0e3eb; }
        
        #workspace { display: flex; flex: 1; position: relative; overflow: hidden; }
        #toolbar { width: 52px; background: #0b0e14; border-right: 1px solid #2B2B43; display: flex; flex-direction: column; align-items: center; padding-top: 10px; gap: 6px; z-index: 10; transition: 0.3s; flex-shrink: 0; }
        body.light-theme #toolbar { background: #ffffff; border-right: 1px solid #e0e3eb; }
        
        .tool-wrapper { position: relative; display: flex; align-items: center; width: 42px; height: 42px; border-radius: 6px; transition: 0.2s; color: #929aa5; }
        body.light-theme .tool-wrapper { color: #787b86; }
        .tool-wrapper:hover { background: #2B2B43; color: #d1d4dc; }
        body.light-theme .tool-wrapper:hover { background: #f0f3fa; color: #131722; }
        .tool-wrapper.active { color: #2962FF; background: rgba(41, 98, 255, 0.15); }
        .tool-main { flex: 1; display: flex; align-items: center; justify-content: center; height: 100%; cursor: pointer; }
        .tool-main svg { width: 22px; height: 22px; stroke: currentColor; fill: none; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
        .tool-arrow { position: absolute; right: 0; bottom: 0; width: 12px; height: 12px; display: flex; align-items: center; justify-content: center; cursor: pointer; border-radius: 0 0 6px 0; }
        .tool-arrow svg { width: 6px; height: 6px; fill: currentColor; stroke: none; }
        .tool-arrow:hover { background: rgba(255,255,255,0.1); }
        body.light-theme .tool-arrow:hover { background: rgba(0,0,0,0.1); }
        .tool-divider { width: 24px; height: 1px; background: #2B2B43; margin: 6px 0; }
        body.light-theme .tool-divider { background: #e0e3eb; }
        
        .flyout-menu { display: none; position: absolute; left: 52px; top: 0; background: #1e222d; border: 1px solid #2B2B43; border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,0.6); z-index: 100; padding: 8px 0; width: 220px;}
        body.light-theme .flyout-menu { background: #ffffff; border: 1px solid #e0e3eb; box-shadow: 0 6px 20px rgba(0,0,0,0.15); }
        .flyout-header { padding: 6px 14px; font-size: 11px; font-weight: bold; color: #787b86; text-transform: uppercase; letter-spacing: 0.5px; }
        .flyout-item { padding: 8px 14px; font-size: 13px; color: #d1d4dc; cursor: pointer; display: flex; align-items: center; gap: 10px; transition: 0.15s; }
        body.light-theme .flyout-item { color: #131722; }
        .flyout-item:hover { background: #2a2e39; color: #fff; }
        body.light-theme .flyout-item:hover { background: #f0f3fa; color: #2962FF; }
        .flyout-item svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 1.5; }

        #main-area { flex: 1; display: flex; flex-direction: column; position: relative; overflow: hidden; }
        #chart-container { flex: 1; position: relative; overflow: hidden; }
        #tv-chart { width: 100%; height: 100%; position: absolute; top: 0; left: 0; z-index: 1; }
        #drawing-layer { position: absolute; top: 0; left: 0; pointer-events: none; z-index: 2; }
        
        #legend { position: absolute; top: 12px; left: 16px; z-index: 5; font-size: 13px; color: #d1d4dc; pointer-events: none; display: flex; flex-direction: column; gap: 4px; }
        body.light-theme #legend { color: #131722; }
        .leg-row { display: flex; gap: 12px; align-items: center; font-weight: 500;}
        .leg-up { color: #26a69a; } .leg-down { color: #ef5350; }
        
        #indicator-legend { display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
        .ind-leg-row { display: flex; align-items: center; font-size: 13px; padding: 2px 0; pointer-events: auto; }
        .ind-leg-title { font-weight: 600; margin-right: 8px; cursor: pointer; color: #d1d4dc; }
        body.light-theme .ind-leg-title { color: #131722; }
        .ind-leg-val { font-weight: 600; margin-right: 12px; }
        .ind-actions { display: none; align-items: center; gap: 6px; }
        .ind-leg-row:hover .ind-actions { display: flex; }
        .ind-btn { cursor: pointer; color: #787b86; transition: 0.2s; display: flex; align-items: center; }
        .ind-btn:hover { color: #d1d4dc; }
        body.light-theme .ind-btn:hover { color: #131722; }
        .ind-btn svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 1.5; }

        #scale-toggles { position: absolute; bottom: 8px; right: 8px; display: flex; gap: 4px; z-index: 50; }
        .scale-btn { width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 12px; color: #929aa5; transition: 0.15s; background: rgba(30, 34, 45, 0.8); backdrop-filter: blur(2px); }
        body.light-theme .scale-btn { background: rgba(240, 243, 250, 0.8); color: #787b86; }
        .scale-btn:hover { color: #fff; background: #2B2B43; }
        body.light-theme .scale-btn:hover { color: #131722; background: #e0e3eb; }
        .scale-btn.active, body.light-theme .scale-btn.active { background: #2962FF !important; color: #ffffff !important; }

        #context-menu { display: none; position: absolute; top: -1000px; left: -1000px; background: #1e222d; border: 1px solid #2B2B43; border-radius: 6px; padding: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.4); z-index: 50; flex-direction: row; gap: 2px; align-items: center; color: #d1d4dc; font-size: 13px; font-weight: 500; pointer-events: auto; }
        body.light-theme #context-menu { background: #ffffff; border: 1px solid #e0e3eb; box-shadow: 0 2px 8px rgba(0,0,0,0.2); color: #131722; }
        .ctx-icon { cursor: pointer; padding: 6px; border-radius: 4px; display: flex; align-items: center; justify-content: center; transition: 0.15s; position: relative; color: #d1d4dc; }
        body.light-theme .ctx-icon { color: #131722; }
        .ctx-icon:hover { background: #2a2e39; }
        body.light-theme .ctx-icon:hover { background: #f0f3fa; }
        .ctx-icon svg { width: 18px; height: 18px; stroke: currentColor; fill: none; stroke-width: 1.5; }
        .ctx-divider { width: 1px; height: 16px; background: #2B2B43; margin: 0 2px; }
        body.light-theme .ctx-divider { background: #e0e3eb; }
        
        .ctx-dropdown { display: none; position: absolute; top: 100%; left: 0; margin-top: 4px; background: #1e222d; border: 1px solid #2B2B43; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.4); padding: 4px 0; z-index: 51; min-width: 120px; flex-direction: column; }
        body.light-theme .ctx-dropdown { background: #ffffff; border: 1px solid #e0e3eb; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .ctx-drop-item { padding: 8px 16px; cursor: pointer; display: flex; align-items: center; transition: 0.1s; color: #d1d4dc; white-space: nowrap; }
        body.light-theme .ctx-drop-item { color: #131722; }
        .ctx-drop-item:hover { background: #2a2e39; color: #fff; }
        body.light-theme .ctx-drop-item:hover { background: #f0f3fa; color: #2962FF; }
        .color-dot { width: 16px; height: 16px; border-radius: 50%; display: inline-block; cursor: pointer; border: 1px solid #434651; }
        body.light-theme .color-dot { border: 1px solid #d1d4dc; }

        #bottom-bar { height: 34px; background: #131722; border-top: 1px solid #2B2B43; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; z-index: 20; font-size: 12px; color: #929aa5; transition: 0.3s; flex-shrink: 0; }
        body.light-theme #bottom-bar { background: #ffffff; border-top: 1px solid #e0e3eb; color: #787b86; }
        .bb-ranges { display: flex; gap: 4px; }
        .bb-range { padding: 4px 8px; cursor: pointer; border-radius: 4px; transition: 0.2s; font-weight: 500; }
        .bb-range:hover { color: #fff; background: #2B2B43; }
        body.light-theme .bb-range:hover { color: #131722; background: #f0f3fa; }
        .bb-right { display: flex; align-items: center; gap: 8px; }
        .bb-clock { font-family: monospace; font-size: 13px; color: #d1d4dc; }
        body.light-theme .bb-clock { color: #131722; }

        /* STRATEGY TESTER PANEL + RESIZER */
        #strategy-tester { position: relative; height: 38px; background: #131722; border-top: 1px solid #2B2B43; display: flex; flex-direction: column; z-index: 15; flex-shrink: 0; overflow: hidden; transition: height 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        body.light-theme #strategy-tester { background: #ffffff; border-top: 1px solid #e0e3eb; }
        
        #st-resizer { position: absolute; top: -2px; left: 0; width: 100%; height: 5px; cursor: ns-resize; z-index: 100; transition: background 0.2s; }
        #st-resizer:hover { background: rgba(41, 98, 255, 0.6); }

        .st-header { height: 38px; min-height: 38px; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; cursor: pointer; border-bottom: 1px solid transparent; transition: 0.2s; }
        #strategy-tester.open .st-header { border-bottom: 1px solid #2B2B43; background: #1e222d; }
        body.light-theme #strategy-tester.open .st-header { border-bottom: 1px solid #e0e3eb; background: #f8f9fa; }
        .st-header:hover { background: rgba(255,255,255,0.03); }
        .st-title-wrap { display: flex; align-items: center; gap: 8px; color: #d1d4dc; }
        body.light-theme .st-title-wrap { color: #131722; }
        .st-title-wrap svg { width: 18px; height: 18px; stroke: currentColor; fill: none; stroke-width: 2; }
        .st-title { font-weight: 600; font-size: 13px; }
        .st-controls { display: flex; gap: 12px; color: #787b86; }
        .st-icon-btn { cursor: pointer; display: flex; align-items: center; transition: 0.2s; }
        .st-icon-btn:hover { color: #d1d4dc; }
        body.light-theme .st-icon-btn:hover { color: #131722; }
        
        .st-toolbar { display: flex; align-items: center; padding: 0 16px; height: 40px; min-height: 40px; border-bottom: 1px solid #2B2B43; gap: 16px; background: #1e222d; }
        body.light-theme .st-toolbar { background: #ffffff; border-bottom: 1px solid #e0e3eb; }
        
        .st-pill-toggle { display: flex; background: #131722; border: 1px solid #2B2B43; border-radius: 6px; padding: 2px; }
        body.light-theme .st-pill-toggle { background: #f0f3fa; border: 1px solid #e0e3eb; }
        .st-pill-btn { padding: 4px 12px; cursor: pointer; border-radius: 4px; color: #787b86; display: flex; align-items: center; justify-content: center; transition: 0.2s; }
        .st-pill-btn svg { width: 18px; height: 18px; stroke: currentColor; fill: none; stroke-width: 1.5; }
        .st-pill-btn.active { background: #2B2B43; color: #d1d4dc; }
        body.light-theme .st-pill-btn.active { background: #ffffff; color: #131722; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
        
        .st-toolbar-btn { display: flex; align-items: center; gap: 6px; cursor: pointer; padding: 6px 12px; border-radius: 4px; font-size: 13px; color: #d1d4dc; transition: 0.2s; }
        .st-toolbar-btn:hover { background: #2B2B43; }
        body.light-theme .st-toolbar-btn { color: #131722; }
        body.light-theme .st-toolbar-btn:hover { background: #f0f3fa; }
        .st-popup { display: none; position: absolute; top: 100%; left: 0; margin-top: 4px; background: #1e222d; border: 1px solid #2B2B43; border-radius: 6px; padding: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.4); z-index: 100; color: #d1d4dc; }
        body.light-theme .st-popup { background: #ffffff; border: 1px solid #e0e3eb; color: #131722; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .st-popup input { background: #131722; border: 1px solid #2B2B43; color: #d1d4dc; padding: 6px 10px; border-radius: 4px; width: 100px; outline: none; font-family: inherit; }
        body.light-theme .st-popup input { background: #f0f3fa; border: 1px solid #e0e3eb; color: #131722; }
        .st-popup select { background: #131722; border: 1px solid #2B2B43; color: #d1d4dc; padding: 6px 10px; border-radius: 4px; outline: none; font-family: inherit; }
        body.light-theme .st-popup select { background: #f0f3fa; border: 1px solid #e0e3eb; color: #131722; }
        
        .st-content { flex: 1; display: flex; overflow: hidden; background: #131722; }
        body.light-theme .st-content { background: #ffffff; }
        
        #st-overview { width: 100%; display: flex; }
        .st-metrics-panel { width: 100%; padding: 24px 32px; display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 24px; border: none; overflow-y: auto; }
        .st-metric { display: flex; flex-direction: column; gap: 4px; }
        .st-metric-label { font-size: 12px; color: #787b86; font-weight: 600; text-transform: uppercase; }
        .st-metric-val { font-size: 24px; font-weight: bold; color: #d1d4dc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Helvetica Neue", sans-serif; }
        body.light-theme .st-metric-val { color: #131722; }
        .val-up { color: #26a69a !important; }
        .val-down { color: #ef5350 !important; }
        
        #st-trades { width: 100%; overflow-y: auto; display: none; }
        .st-table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
        .st-table th { position: sticky; top: 0; background: #1e222d; color: #787b86; padding: 8px 16px; border-bottom: 1px solid #2B2B43; font-weight: normal; z-index: 2; white-space: nowrap; }
        body.light-theme .st-table th { background: #f8f9fa; border-bottom: 1px solid #e0e3eb; }
        .st-table td { padding: 8px 16px; border-bottom: 1px solid #2B2B43; color: #d1d4dc; }
        body.light-theme .st-table td { border-bottom: 1px solid #e0e3eb; color: #131722; }
        .st-table tr:hover td { background: rgba(255,255,255,0.03); }
        body.light-theme .st-table tr:hover td { background: rgba(0,0,0,0.02); }

        /* MODALS */
        .modal { display: none; position: absolute; top: 60px; left: 50%; transform: translateX(-50%); background: #1e222d; border: 1px solid #2B2B43; border-radius: 8px; padding: 20px; z-index: 100; box-shadow: 0 8px 24px rgba(0,0,0,0.6); }
        body.light-theme .modal { background: #ffffff; border: 1px solid #e0e3eb; box-shadow: 0 8px 24px rgba(0,0,0,0.15); color: #131722; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: bold; margin-bottom: 20px; color: #fff; border-bottom: 1px solid #2B2B43; padding-bottom: 10px; }
        body.light-theme .modal-header { color: #131722; border-bottom: 1px solid #e0e3eb; }
        .close-btn { cursor: pointer; color: #929aa5; display: flex; align-items: center; } .close-btn:hover { color: #ef5350; }
        .settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; font-size: 13px; color: #d1d4dc; }
        body.light-theme .settings-grid { color: #131722; }
        .setting-item { display: flex; justify-content: space-between; align-items: center; }
        .setting-item select { background: #131722; color: #d1d4dc; border: 1px solid #2B2B43; padding: 4px 8px; border-radius: 4px; outline: none; }
        body.light-theme .setting-item select { background: #f0f3fa; color: #131722; border: 1px solid #e0e3eb; }
        .switch { position: relative; display: inline-block; width: 34px; height: 18px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #2B2B43; transition: .4s; border-radius: 18px; }
        body.light-theme .slider { background-color: #e0e3eb; }
        .slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 2px; bottom: 2px; background-color: #787b86; transition: .4s; border-radius: 50%; }
        input:checked + .slider { background-color: #2962FF; }
        input:checked + .slider:before { transform: translateX(16px); background-color: #fff; }
        .ind-item { padding: 10px; cursor: pointer; border-radius: 4px; transition: 0.2s; display: flex; justify-content: space-between; align-items: center; color: #d1d4dc; }
        body.light-theme .ind-item { color: #131722; }
        .ind-item:hover { background: #2a2e39; color: #fff; }
        body.light-theme .ind-item:hover { background: #f0f3fa; color: #2962FF; }
    </style>
</head>
<body>
    
    <div id="top-bar">
        <div class="tb-group">
            <div class="tb-btn tb-text-bold">BANKNIFTY</div>
            <div class="divider"></div>
            <div class="tb-btn tb-text-bold">1m</div>
            <div class="divider"></div>
            <div class="tb-btn" onclick="toggleModal('indicators-modal')"><svg viewBox="0 0 24 24"><path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 6-6"/></svg> Indicators</div>
            <div class="divider"></div>
            <div class="tb-btn" onclick="undoLastAction()" title="Undo"><svg viewBox="0 0 24 24"><path d="M9 14l-4-4 4-4"/><path d="M5 10h11a4 4 0 1 1 0 8h-1"/></svg></div>
            <div class="tb-btn" onclick="redoLastAction()" title="Redo"><svg viewBox="0 0 24 24"><path d="M15 14l4-4-4-4"/><path d="M19 10H8a4 4 0 1 0 0 8h1"/></svg></div>
        </div>
        <div class="tb-group">
            
            <div class="tb-btn" onclick="openPineEditor()" title="Pine Editor">
                <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="8 17 12 11 16 17" />
                    <polyline points="3 17 9 7 15 15" />
                    <line x1="3" y1="17" x2="21" y2="17" />
                </svg>
            </div>
            
            <div class="tb-btn" onclick="toggleModal('settings-modal')"><svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg></div>
            <div class="tb-btn" onclick="takeScreenshot()"><svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"/></svg></div>
        </div>
    </div>

    <div id="workspace">
        <div id="toolbar">
            <div class="tool-wrapper active" id="btn-group-cursor"><div class="tool-main" onclick="setTool(null, event)"><svg viewBox="0 0 24 24"><path d="M12 4v16M4 12h16"/></svg></div></div>
            <div class="tool-wrapper" id="btn-group-trend">
                <div class="tool-main" onclick="setTool('trend', event)"><svg viewBox="0 0 24 24"><path d="M5 19L19 5"/><circle cx="5" cy="19" r="1.5" fill="currentColor"/><circle cx="19" cy="5" r="1.5" fill="currentColor"/></svg></div>
                <div class="tool-arrow" onclick="toggleFlyout('trend-flyout', event)"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>
                <div id="trend-flyout" class="flyout-menu">
                    <div class="flyout-header">Line Tools</div>
                    <div class="flyout-item" onclick="setTool('trend', event)"><svg viewBox="0 0 24 24"><path d="M5 19L19 5"/><circle cx="5" cy="19" r="1.5"/><circle cx="19" cy="5" r="1.5"/></svg> Trend Line</div>
                    <div class="flyout-item" onclick="setTool('hline', event)"><svg viewBox="0 0 24 24"><path d="M4 12h16"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></svg> Horizontal Line</div>
                </div>
            </div>
            <div class="tool-wrapper" id="btn-group-fib">
                <div class="tool-main" onclick="setTool('fib', event)"><svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16"/></svg></div>
                <div class="tool-arrow" onclick="toggleFlyout('fib-flyout', event)"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>
                <div id="fib-flyout" class="flyout-menu">
                    <div class="flyout-header">Fibonacci</div>
                    <div class="flyout-item" onclick="setTool('fib', event)"><svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16"/></svg> Fib Retracement</div>
                </div>
            </div>
            <div class="tool-wrapper" id="btn-group-patterns">
                <div class="tool-main" onclick="setTool('cyclic', event)"><svg viewBox="0 0 24 24"><circle cx="6" cy="16" r="1.5" fill="currentColor"/><circle cx="10" cy="8" r="1.5" fill="currentColor"/><circle cx="14" cy="16" r="1.5" fill="currentColor"/><circle cx="18" cy="8" r="1.5" fill="currentColor"/><path d="M6.5 14.5l3-5M10.5 9.5l3 5M14.5 14.5l3-5"/></svg></div>
                <div class="tool-arrow" onclick="toggleFlyout('patterns-flyout', event)"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>
                <div id="patterns-flyout" class="flyout-menu">
                    <div class="flyout-header">Cycles</div>
                    <div class="flyout-item" onclick="setTool('cyclic', event)"><svg viewBox="0 0 24 24"><path d="M6 6v12M10 6v12M14 6v12M18 6v12"/><line x1="4" y1="18" x2="20" y2="18"/></svg> Cyclic lines</div>
                </div>
            </div>
            <div class="tool-wrapper" id="btn-measure">
                <div class="tool-main" onclick="setTool('measure', event)"><svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="1.5"><path d="M17 5L19 7L7 19L5 17Z" stroke-linejoin="round"/><path d="M15 7L16 8M13 9L14 10M11 11L12 12M9 13L10 14"/></svg></div>
            </div>
            <div class="tool-divider"></div>
            <div class="tool-wrapper" id="btn-global-lock" onclick="toggleGlobalLock()"><div class="tool-main"><svg viewBox="0 0 24 24"><rect x="6" y="11" width="12" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg></div></div>
            <div class="tool-wrapper" onclick="clearDrawings()"><div class="tool-main"><svg viewBox="0 0 24 24"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"/></svg></div></div>
        </div>

        <div id="main-area">
            <div id="chart-container">
                <div id="legend">
                    <div class="leg-row">
                        <span>O <span class="leg-val" id="leg-o">-</span></span>
                        <span>H <span class="leg-val" id="leg-h">-</span></span>
                        <span>L <span class="leg-val" id="leg-l">-</span></span>
                        <span>C <span class="leg-val" id="leg-c">-</span></span>
                        <span id="leg-chg" style="margin-left: 8px;">-</span>
                    </div>
                    <div id="indicator-legend"></div>
                    
                    <div id="strategy-legend" class="ind-leg-row" style="display:none; margin-top:4px;">
                        <span class="ind-leg-title" id="legend-strategy-title" style="color: #2962FF;">BANKNIFTY Direct CD Simple</span>
                        <div class="ind-actions" style="display: flex;">
                            <div class="ind-btn" onclick="toggleStrategyVis()" title="Show/Hide">
                                <svg id="eye-icon" viewBox="0 0 24 24" width="16" height="16"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" fill="none" stroke-width="1.5"/><circle cx="12" cy="12" r="3" stroke="currentColor" fill="none" stroke-width="1.5"/></svg>
                            </div>
                            <div class="ind-btn" onclick="removeStrategy()" title="Remove Strategy">
                                <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" fill="none" stroke-width="1.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div id="tv-chart"></div>
                <canvas id="drawing-layer"></canvas>
                
                <div id="scale-toggles">
                    <div class="scale-btn active" id="btn-scale-a" onclick="toggleAutoScale()">A</div>
                    <div class="scale-btn" id="btn-scale-l" onclick="toggleLogScale()">L</div>
                </div>

                <div id="context-menu" style="display: none; top: -1000px; left: -1000px;">
                    <div class="ctx-icon" style="padding: 4px;" onclick="toggleCtxMenu('ctx-color-drop', event)"><div class="color-dot" id="active-color-dot" style="background:#2962FF;"></div><div class="ctx-dropdown" id="ctx-color-drop" style="flex-direction:row; padding:6px; gap:4px; min-width:auto;"><div class="color-dot" style="background:#2962FF;" onclick="changeColor('#2962FF')"></div><div class="color-dot" style="background:#ef5350;" onclick="changeColor('#ef5350')"></div><div class="color-dot" style="background:#26a69a;" onclick="changeColor('#26a69a')"></div><div class="color-dot" style="background:#f59e0b;" onclick="changeColor('#f59e0b')"></div></div></div>
                    <div class="ctx-divider"></div>
                    <div class="ctx-icon" onclick="toggleCtxMenu('ctx-width-drop', event)"><span id="active-width-label" style="font-weight: 600; font-size: 13px; width: 24px; text-align: center;">2px</span><div class="ctx-dropdown" id="ctx-width-drop"><div class="ctx-drop-item" onclick="changeWidth(1)">1px</div><div class="ctx-drop-item" onclick="changeWidth(2)">2px</div><div class="ctx-drop-item" onclick="changeWidth(3)">3px</div><div class="ctx-drop-item" onclick="changeWidth(4)">4px</div></div></div>
                    <div class="ctx-icon" onclick="toggleCtxMenu('ctx-style-drop', event)"><svg viewBox="0 0 24 24"><path d="M4 12h16"/></svg><div class="ctx-dropdown" id="ctx-style-drop"><div class="ctx-drop-item" onclick="changeStyle('solid')"><svg viewBox="0 0 24 24" style="width:20px;height:20px;margin-right:8px;"><path d="M4 12h16"/></svg> Line</div><div class="ctx-drop-item" onclick="changeStyle('dashed')"><svg viewBox="0 0 24 24" style="width:20px;height:20px;margin-right:8px;"><path d="M4 12h4M10 12h4M16 12h4"/></svg> Dashed Line</div><div class="ctx-drop-item" onclick="changeStyle('dotted')"><svg viewBox="0 0 24 24" style="width:20px;height:20px;margin-right:8px;"><circle cx="6" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="18" cy="12" r="1.5" fill="currentColor"/></svg> Dotted Line</div></div></div>
                    <div class="ctx-divider"></div>
                    <div class="ctx-icon" id="ctx-btn-lock" title="Lock Item" onclick="toggleItemLock()"><svg viewBox="0 0 24 24"><rect x="6" y="11" width="12" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg></div>
                    <div class="ctx-icon" style="color: #ef5350;" onclick="deleteSelectedDrawing()"><svg viewBox="0 0 24 24"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"/></svg></div>
                </div>
            </div>
            
            <div id="bottom-bar">
                <div class="bb-ranges">
                    <div class="bb-range" onclick="zoomRange('1D')">1D</div>
                    <div class="bb-range" onclick="zoomRange('7D')">7D</div>
                    <div class="bb-range" onclick="zoomRange('1M')">1M</div>
                    <div class="bb-range" onclick="zoomRange('3M')">3M</div>
                    <div class="bb-range" onclick="zoomRange('ALL')">ALL</div>
                </div>
                <div class="bb-right">
                    <span class="bb-clock" id="live-clock">00:00:00 UTC+5:30 (IST)</span>
                    <span style="font-weight:600; color:#d1d4dc;">RTH</span>
                </div>
            </div>

            <div id="strategy-tester" class="open" style="display:none; height: 300px;">
                <div id="st-resizer"></div>
                
                <div class="st-header" onclick="toggleTester()">
                    <div class="st-title-wrap"><svg viewBox="0 0 24 24"><path d="M3 17l6-6 4 4 8-8" stroke="currentColor" fill="none" stroke-width="2"/></svg><span class="st-title" id="panel-strategy-title">BANKNIFTY Direct CD Simple</span><svg viewBox="0 0 24 24" style="width:14px;height:14px;"><path d="M6 9l6 6 6-6"/></svg></div>
                    <div class="st-controls"><div class="st-icon-btn"><svg viewBox="0 0 24 24" width="18" height="18"><path d="M5 12h14" stroke="currentColor" stroke-width="2"/></svg></div><div class="st-icon-btn"><svg viewBox="0 0 24 24" width="16" height="16"><rect x="4" y="4" width="16" height="16" rx="2" stroke="currentColor" fill="none" stroke-width="2"/></svg></div></div>
                </div>
                <div class="st-toolbar">
                    <div class="st-pill-toggle">
                        <div class="st-pill-btn active" id="btn-tab-overview" onclick="switchStTab('overview')" title="Overview"><svg viewBox="0 0 24 24"><path d="M3 17l6-6 4 4 8-8" stroke="currentColor" fill="none" stroke-width="2"/></svg></div>
                        <div class="st-pill-btn" id="btn-tab-list" onclick="switchStTab('list')" title="List of Trades"><svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" fill="none" stroke-width="2"/></svg></div>
                    </div>
                    <div class="divider" style="height:16px;"></div>
                    <div style="position:relative;">
                        <div class="st-toolbar-btn" onclick="toggleCapitalPopup(event)"><svg viewBox="0 0 24 24" width="16" height="16"><circle cx="12" cy="12" r="10" stroke="currentColor" fill="none" stroke-width="1.5"/><path d="M12 8v8M9 12h6" stroke="currentColor" stroke-width="1.5"/></svg> 100 K Same as chart <svg viewBox="0 0 24 24" width="12" height="12"><path d="M6 9l6 6 6-6" stroke="currentColor" fill="none" stroke-width="2"/></svg></div>
                        <div id="capital-popup" class="st-popup">
                            <div style="font-weight:600; font-size:12px; margin-bottom:10px;">Initial capital</div>
                            <div style="display:flex; gap:8px;"><input type="text" value="100,000"><select><option>Same as chart</option></select></div>
                        </div>
                    </div>
                </div>
                
                <div class="st-content" id="st-overview">
                    <div class="st-metrics-panel">
                        <div class="st-metric"><span class="st-metric-label">Net Profit</span><span class="st-metric-val" id="metric-pnl">-</span></div>
                        <div class="st-metric"><span class="st-metric-label">Total Closed Trades</span><span class="st-metric-val" id="metric-trades">-</span></div>
                        <div class="st-metric"><span class="st-metric-label">Percent Profitable</span><span class="st-metric-val" id="metric-winrate">-</span></div>
                        <div class="st-metric"><span class="st-metric-label">Profit Factor</span><span class="st-metric-val" id="metric-pf">-</span></div>
                        <div class="st-metric"><span class="st-metric-label">Max Drawdown</span><span class="st-metric-val val-down" id="metric-dd">-</span></div>
                    </div>
                </div>
                <div class="st-content" id="st-list" style="display:none; overflow-y:auto;">
                    <table class="st-table">
                        <thead><tr>
                            <th onclick="toggleTradeSort()" style="cursor:pointer; user-select:none;">Trade # <svg id="sort-arrow" viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" fill="none" stroke-width="2" style="vertical-align:middle; transition: 0.2s;"><path d="M12 19V5M5 12l7-7 7 7"/></svg></th>
                            <th>Type</th><th>Entry Time</th><th>Exit Time</th><th>Entry Price</th><th>Exit Price</th><th>Profit/Loss</th><th>Cum. Equity</th>
                        </tr></thead>
                        <tbody id="trade-table-body"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- PINE EDITOR MODAL OVERLAY -->
    <div id="pine-editor-overlay" style="display: none; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); z-index: 9999; align-items: center; justify-content: center; backdrop-filter: blur(2px);">
        <div style="width: 80%; height: 80%; background: #131722; border: 1px solid #2B2B43; border-radius: 8px; display: flex; flex-direction: column; box-shadow: 0 10px 30px rgba(0,0,0,0.5); overflow: hidden;">
            <div style="height: 48px; border-bottom: 1px solid #2B2B43; display: flex; justify-content: space-between; align-items: center; padding: 0 20px; background: #1e222d;">
                <div style="font-weight: bold; color: #d1d4dc; font-size: 15px; display: flex; align-items: center; gap: 8px;">
                    <svg viewBox="0 0 28 28" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M10 13.5L14 9.5L18 13.5" stroke-linecap="round" stroke-linejoin="round"/>
                        <path d="M7 19.5L10 15H18L21 19.5H7Z" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    Pine Script Editor
                </div>
                <div style="display:flex; gap:16px; align-items:center;">
                    <button id="run-pine-btn" onclick="executePineScript()" style="background: #2962FF; color: white; border: none; padding: 8px 24px; border-radius: 4px; font-weight: bold; cursor: pointer;">Run Script</button>
                    <div onclick="document.getElementById('pine-editor-overlay').style.display='none'" style="cursor: pointer; color: #929aa5; display:flex; align-items:center;" title="Close">
                        <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
                    </div>
                </div>
            </div>
            <div id="monaco-overlay-container" style="flex: 1; width: 100%;"></div>
        </div>
    </div>

    <!-- MODALS -->
    <div id="indicators-modal" class="modal" style="width: 280px;">
        <div class="modal-header"><span>Indicators</span><span class="close-btn" onclick="toggleModal('indicators-modal')"><svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg></span></div>
        <div class="ind-item" onclick="applyIndicator('SMA')"><span>Moving Average Simple</span><span style="color:#2962FF;">+</span></div>
        <div class="ind-item" onclick="applyIndicator('EMA')"><span>Moving Average Exponential</span><span style="color:#2962FF;">+</span></div>
    </div>

    <div id="settings-modal" class="modal" style="width: 420px;">
        <div class="modal-header"><span>Setting</span><span class="close-btn" onclick="toggleModal('settings-modal')"><svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg></span></div>
        <div class="settings-grid">
            <div class="setting-item"><span>candle_type</span><select id="set-candle-type" onchange="applyGlobalSettings()"><option value="solid">candle_solid</option><option value="hollow">candle_hollow</option></select></div>
            <div class="setting-item"><span>grid_show</span><label class="switch"><input type="checkbox" id="set-grid" checked onchange="applyGlobalSettings()"><span class="slider"></span></label></div>
            <div class="setting-item"><span>Background</span><select id="set-bg" onchange="applyGlobalSettings()"><option value="dark">Dark</option><option value="light">Light</option></select></div>
            <div class="setting-item" style="grid-column: 1 / -1; display:flex; justify-content:space-between; align-items:center; margin-top: 8px;">
                <span style="font-size: 14px;">Session breaks</span>
                <div style="display:flex; align-items:center; gap: 12px;">
                    <label class="switch"><input type="checkbox" id="set-session" onchange="applyGlobalSettings()"><span class="slider"></span></label>
                    <div style="border: 1px solid #2B2B43; border-radius: 4px; padding: 4px 8px; display:flex; gap:8px; align-items:center; cursor:pointer;" id="sess-box">
                        <div id="sess-color-node" style="width:16px; height:16px; background:#2962FF; border-radius:2px;" onclick="cycleSessionColor()"></div>
                        <div id="sess-style-node" style="width:24px; text-align:center; font-weight:bold; color:#2962FF; line-height:1;" onclick="cycleSessionStyle()">—</div>
                    </div>
                </div>
            </div>
        </div>
        <div style="display:flex; justify-content:flex-end; margin-top: 24px;"><button style="background:#2962FF; color:#fff; border:none; padding:8px 16px; border-radius:4px; cursor:pointer; font-weight:bold;" onclick="restoreDefaults()">restore_default</button></div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.39.0/min/vs/loader.min.js"></script>
    <script>
        const chartData = __CHART_DATA__;
        
        let strategyMarkers = [];
        let strategyCycleData = [];
        let strategyTrades = [];
        
        let activeTool = null; let drawings = []; let currentPoints = [];
        let actionHistory = []; let redoHistory = []; let activeIndicators = [];
        let selectedDrawingIndex = -1;
        let isGlobalLocked = false; let isAuto = true; let isLog = false;
        
        let isStrategyVisible = false; 
        
        let sessionActive = false; let sessionColorIdx = 0; const sColors = ['#2962FF', '#ef5350', '#26a69a', '#787b86']; let sessionStyleIdx = 1; const sStyles = ['solid', 'dashed', 'dotted']; let sessionBreakPoints = [];

        let currentDay = -1;
        for (let i = 0; i < chartData.length; i++) {
            let d = new Date(chartData[i].time * 1000); let day = d.getDate();
            if (day !== currentDay) { if (currentDay !== -1) sessionBreakPoints.push(chartData[i].time); currentDay = day; }
        }

        window.cycleSessionColor = function() { sessionColorIdx = (sessionColorIdx + 1) % sColors.length; document.getElementById('sess-color-node').style.background = sColors[sessionColorIdx]; document.getElementById('sess-style-node').style.color = sColors[sessionColorIdx]; applyGlobalSettings(); };
        window.cycleSessionStyle = function() { sessionStyleIdx = (sessionStyleIdx + 1) % sStyles.length; const node = document.getElementById('sess-style-node'); if(sStyles[sessionStyleIdx] === 'solid') node.innerText = '—'; else if(sStyles[sessionStyleIdx] === 'dashed') node.innerText = '---'; else node.innerText = '•••'; applyGlobalSettings(); };

        window.applyGlobalSettings = function() {
            const isLight = document.getElementById('set-bg').value === 'light'; const showGrid = document.getElementById('set-grid').checked; const isHollow = document.getElementById('set-candle-type').value === 'hollow'; sessionActive = document.getElementById('set-session').checked;
            if(isLight) { document.body.classList.add('light-theme'); chart.applyOptions({ layout: { background: { color: '#ffffff' }, textColor: '#131722' }, grid: { vertLines: { color: showGrid ? '#e0e3eb' : 'transparent' }, horzLines: { color: showGrid ? '#e0e3eb' : 'transparent' } } }); } 
            else { document.body.classList.remove('light-theme'); chart.applyOptions({ layout: { background: { color: '#131722' }, textColor: '#d1d4dc' }, grid: { vertLines: { color: showGrid ? '#2B2B43' : 'transparent' }, horzLines: { color: showGrid ? '#2B2B43' : 'transparent' } } }); }
            if (isHollow) { series.applyOptions({ upColor: 'transparent', wickUpColor: '#26a69a', borderUpColor: '#26a69a', borderVisible: true }); } else { series.applyOptions({ upColor: '#26a69a', wickUpColor: '#26a69a', borderVisible: false }); }
        };

        window.restoreDefaults = function() { document.getElementById('set-bg').value = 'dark'; document.getElementById('set-grid').checked = true; document.getElementById('set-candle-type').value = 'solid'; document.getElementById('set-session').checked = false; sessionColorIdx = 0; sessionStyleIdx = 1; document.getElementById('sess-color-node').style.background = sColors[0]; document.getElementById('sess-style-node').style.color = sColors[0]; document.getElementById('sess-style-node').innerText = '---'; applyGlobalSettings(); };

        function toggleFlyout(id, e) { if(e) e.stopPropagation(); const menu = document.getElementById(id); const isOpen = menu.style.display === 'block'; document.querySelectorAll('.flyout-menu').forEach(m => m.style.display = 'none'); menu.style.display = isOpen ? 'none' : 'block'; }
        function toggleCtxMenu(id, e) { if(e) e.stopPropagation(); const drop = document.getElementById(id); const isOpen = drop.style.display === 'flex'; document.querySelectorAll('.ctx-dropdown').forEach(d => d.style.display = 'none'); drop.style.display = isOpen ? 'none' : 'flex'; }
        window.toggleCapitalPopup = function(e) { if(e) e.stopPropagation(); const pop = document.getElementById('capital-popup'); pop.style.display = pop.style.display === 'block' ? 'none' : 'block'; };

        window.addEventListener('click', (e) => { 
            if (!e.target.closest('.tool-wrapper') && !e.target.closest('.flyout-menu')) { document.querySelectorAll('.flyout-menu').forEach(m => m.style.display = 'none'); } 
            if (!e.target.closest('.ctx-icon')) { document.querySelectorAll('.ctx-dropdown').forEach(m => m.style.display = 'none'); } 
            if (!e.target.closest('#capital-popup') && !e.target.closest('.st-toolbar-btn')) { document.getElementById('capital-popup').style.display = 'none'; }
        });

        window.toggleGlobalLock = function() { isGlobalLocked = !isGlobalLocked; document.getElementById('btn-global-lock').classList.toggle('active', isGlobalLocked); hideContextMenu(); };
        window.toggleItemLock = function() { if (selectedDrawingIndex > -1) { drawings[selectedDrawingIndex].isLocked = !drawings[selectedDrawingIndex].isLocked; document.getElementById('ctx-btn-lock').style.color = drawings[selectedDrawingIndex].isLocked ? '#2962FF' : (document.body.classList.contains('light-theme') ? '#131722' : '#d1d4dc'); } };
        window.toggleAutoScale = function() { isAuto = !isAuto; if (isAuto) { isLog = false; document.getElementById('btn-scale-l').classList.remove('active'); chart.priceScale('right').applyOptions({ mode: LightweightCharts.PriceScaleMode.Normal }); } document.getElementById('btn-scale-a').classList.toggle('active', isAuto); chart.priceScale('right').applyOptions({ autoScale: isAuto }); };
        window.toggleLogScale = function() { isLog = !isLog; if (isLog) { isAuto = false; document.getElementById('btn-scale-a').classList.remove('active'); chart.priceScale('right').applyOptions({ autoScale: false }); } document.getElementById('btn-scale-l').classList.toggle('active', isLog); chart.priceScale('right').applyOptions({ mode: isLog ? LightweightCharts.PriceScaleMode.Logarithmic : LightweightCharts.PriceScaleMode.Normal }); };
        window.undoLastAction = function() { if (actionHistory.length > 0) { const action = actionHistory.pop(); if (action.type === 'DRAWING_ADD') drawings = drawings.filter(d => d !== action.payload); if (action.type === 'INDICATOR_ADD') { action.payload.series.forEach(s => chart.removeSeries(s)); action.payload.legendRow.style.display = 'none'; } redoHistory.push(action); hideContextMenu(); } };
        window.redoLastAction = function() { if (redoHistory.length > 0) { const action = redoHistory.pop(); if (action.type === 'DRAWING_ADD') drawings.push(action.payload); if (action.type === 'INDICATOR_ADD') { action.payload.series.forEach(s => { let newSeries = chart.addLineSeries(s.options()); newSeries.setData(s.data()); }); action.payload.legendRow.style.display = 'flex'; } actionHistory.push(action); hideContextMenu(); } };
        window.clearDrawings = function() { if (drawings.length > 0) { actionHistory.push({ type: 'DRAWING_CLEAR', payload: [...drawings] }); drawings = []; redoHistory = []; hideContextMenu(); }};
        function toggleModal(id) { const el = document.getElementById(id); document.querySelectorAll('.modal').forEach(m => { if(m.id !== id) m.style.display = 'none'; }); el.style.display = (el.style.display === 'block') ? 'none' : 'block'; }

        setInterval(() => { const now = new Date(); const timeStr = now.toLocaleTimeString('en-IN', {hour12: false, timeZone: 'Asia/Kolkata'}); document.getElementById('live-clock').innerText = timeStr + ' UTC+5:30 (IST)'; }, 1000);

        const chartDiv = document.getElementById('tv-chart');
        const canvas = document.getElementById('drawing-layer');
        const ctx = canvas.getContext('2d');
        
        const chart = LightweightCharts.createChart(chartDiv, { layout: { background: { type: 'solid', color: '#131722' }, textColor: '#d1d4dc' }, grid: { vertLines: { color: '#2B2B43' }, horzLines: { color: '#2B2B43' } }, crosshair: { mode: LightweightCharts.CrosshairMode.Normal }, timeScale: { timeVisible: true } });
        const series = chart.addCandlestickSeries({ upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350' });
        series.setData(chartData);

        const resizeObserver = new ResizeObserver(entries => {
            for (let entry of entries) {
                if (entry.target === chartDiv) {
                    chart.resize(entry.contentRect.width, entry.contentRect.height);
                    canvas.width = entry.contentRect.width; canvas.height = entry.contentRect.height;
                }
            }
        });
        resizeObserver.observe(chartDiv);

        const stResizer = document.getElementById('st-resizer');
        const testerPanel = document.getElementById('strategy-tester');
        let isResizing = false;
        let lastPanelHeight = 300;

        stResizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            testerPanel.style.transition = 'none';
            document.body.style.cursor = 'ns-resize';
            document.getElementById('main-area').style.pointerEvents = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            let newHeight = window.innerHeight - e.clientY;
            if (newHeight < 38) newHeight = 38; 
            if (newHeight > window.innerHeight * 0.8) newHeight = window.innerHeight * 0.8;
            
            testerPanel.style.height = newHeight + 'px';
            lastPanelHeight = newHeight;
            
            if (newHeight <= 45) { testerPanel.classList.remove('open'); } 
            else { testerPanel.classList.add('open'); }
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                testerPanel.style.transition = 'height 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
                document.body.style.cursor = 'default';
                document.getElementById('main-area').style.pointerEvents = 'auto';
            }
        });

        let sortAsc = false;
        window.toggleTradeSort = function() {
            sortAsc = !sortAsc;
            document.getElementById('sort-arrow').style.transform = sortAsc ? 'rotate(180deg)' : 'rotate(0deg)';
            strategyTrades.reverse();
            renderTradeList();
        };

        function renderTradeList() {
            const tbody = document.getElementById('trade-table-body');
            if(!tbody) return;
            tbody.innerHTML = '';
            strategyTrades.forEach((t, i) => {
                let actualIndex = sortAsc ? (strategyTrades.length - i) : (i + 1);
                let row = document.createElement('tr');
                let sign = t.pnl >= 0 ? '+' : '';
                let color = t.pnl >= 0 ? '#26a69a' : '#ef5350';
                let sideColor = t.side === 'Long' ? '#2962FF' : '#ef5350';
                let enDt = new Date(t.entry_time * 1000).toLocaleString('en-IN');
                let exDt = new Date(t.exit_time * 1000).toLocaleString('en-IN');
                row.innerHTML = `<td>${actualIndex}</td><td style="color:${sideColor}; font-weight:bold;">${t.side}</td><td>${enDt}</td><td>${exDt}</td><td>${t.entry.toFixed(2)}</td><td>${t.exit.toFixed(2)}</td><td style="color:${color};">${sign}${t.pnl.toFixed(2)}</td><td>${t.equity.toFixed(2)}</td>`;
                tbody.appendChild(row);
            });
        }

        window.toggleStrategyVis = function() {
            isStrategyVisible = !isStrategyVisible;
            
            const tester = document.getElementById('strategy-tester');
            const eye = document.getElementById('eye-icon');
            
            if (isStrategyVisible) {
                if(tester) tester.style.display = 'flex';
                if(strategyMarkers && strategyMarkers.length > 0) series.setMarkers(strategyMarkers);
                if(eye) eye.style.opacity = '1';
            } else {
                if(tester) tester.style.display = 'none';
                series.setMarkers([]);
                if(eye) eye.style.opacity = '0.4';
            }
            requestAnimationFrame(renderDrawings);
        };

        window.removeStrategy = function() {
            strategyTrades = [];
            
            const tester = document.getElementById('strategy-tester');
            if (tester) tester.style.display = 'none';
            
            const leg = document.getElementById('strategy-legend');
            if (leg) leg.style.display = 'none';
            
            isStrategyVisible = false;
            
            series.setMarkers([]);
            strategyMarkers = [];
            
            const pnl = document.getElementById('metric-pnl');
            if(pnl) { pnl.innerText = '-'; pnl.className = 'st-metric-val val-neutral'; }
            
            const trds = document.getElementById('metric-trades');
            if(trds) trds.innerText = '-';
            
            const wr = document.getElementById('metric-winrate');
            if(wr) wr.innerText = '-';
            
            const pf = document.getElementById('metric-pf');
            if(pf) pf.innerText = '-';
            
            const dd = document.getElementById('metric-dd');
            if(dd) { dd.innerText = '-'; dd.className = 'st-metric-val val-neutral'; }
            
            const tbody = document.getElementById('trade-table-body');
            if(tbody) tbody.innerHTML = '';
            
            requestAnimationFrame(renderDrawings);
        };

        window.toggleTester = function() {
            if (testerPanel && testerPanel.classList.contains('open')) {
                testerPanel.classList.remove('open');
                testerPanel.style.height = '38px';
            } else if (testerPanel) {
                testerPanel.classList.add('open');
                testerPanel.style.height = Math.max(lastPanelHeight, 200) + 'px';
            }
        };
        
        window.switchStTab = function(tab) {
            const btnOver = document.getElementById('btn-tab-overview');
            const btnList = document.getElementById('btn-tab-list');
            const stOver = document.getElementById('st-overview');
            const stList = document.getElementById('st-list');
            
            if(btnOver) btnOver.classList.remove('active');
            if(btnList) btnList.classList.remove('active');
            if(stOver) stOver.style.display = 'none';
            if(stList) stList.style.display = 'none';
            
            if(tab === 'overview') {
                if(btnOver) btnOver.classList.add('active');
                if(stOver) stOver.style.display = 'flex';
            } else {
                if(btnList) btnList.classList.add('active');
                if(stList) stList.style.display = 'block';
                renderTradeList();
            }
        };

        const PineTS = { sma: (data, p) => { let res=[]; for(let i=0; i<data.length; i++) { if(i<p-1) continue; let s=0; for(let j=0; j<p; j++) s+=data[i-j].close; res.push({time:data[i].time, value:s/p}); } return res; }, ema: (data, p) => { let res=[]; let k=2/(p+1); let ema=data[0].close; for(let i=0; i<data.length; i++) { ema=(data[i].close*k)+(ema*(1-k)); if(i>=p-1) res.push({time:data[i].time, value:ema}); } return res; } };

        window.applyIndicator = function(type) {
            toggleModal('indicators-modal'); const indId = Date.now(); let indObj = { id: indId, type: type, series: [], domId: `ind-leg-${indId}` }; const row = document.createElement('div'); row.className = 'ind-leg-row'; row.id = indObj.domId; let color = '#2962FF', title = '', valHtml = '';
            if (type === 'SMA') { const line = chart.addLineSeries({ color: color, lineWidth: 2, title: 'SMA 20' }); line.setData(PineTS.sma(chartData, 20)); indObj.series.push(line); title = 'SMA (20)'; valHtml = `<span class="ind-leg-val" id="ind-val-${indId}-0" style="color:${color};">-</span>`; } 
            else if (type === 'EMA') { color = '#f59e0b'; const line = chart.addLineSeries({ color: color, lineWidth: 2, title: 'EMA 9' }); line.setData(PineTS.ema(chartData, 9)); indObj.series.push(line); title = 'EMA (9)'; valHtml = `<span class="ind-leg-val" id="ind-val-${indId}-0" style="color:${color};">-</span>`; }
            row.innerHTML = `<div style="display:flex; align-items:center;"><span class="ind-leg-title">${title}</span>${valHtml}</div><div class="ind-actions"><div class="ind-btn" onclick="toggleVis(${indId})" title="Show/Hide"><svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></div><div class="ind-btn" onclick="removeInd(${indId})" title="Remove"><svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" stroke-linecap="round"/></svg></div></div>`;
            document.getElementById('indicator-legend').appendChild(row); indObj.legendRow = row; activeIndicators.push(indObj); actionHistory.push({ type: 'INDICATOR_ADD', payload: indObj });
        };
        window.removeInd = function(id) { const idx = activeIndicators.findIndex(i => i.id === id); if (idx > -1) { activeIndicators[idx].series.forEach(s => chart.removeSeries(s)); activeIndicators[idx].legendRow.style.display = 'none'; activeIndicators.splice(idx, 1); } };
        window.toggleVis = function(id) { const ind = activeIndicators.find(i => i.id === id); if (ind && ind.series.length > 0) { const isVisible = ind.series[0].options().visible; ind.series.forEach(s => s.applyOptions({visible: !isVisible})); } };

        window.setTool = function(toolName, event) {
            if(event) event.stopPropagation(); document.querySelectorAll('.flyout-menu').forEach(m => m.style.display = 'none'); document.querySelectorAll('.tool-wrapper').forEach(btn => btn.classList.remove('active')); hideContextMenu();
            if (activeTool === toolName || toolName === null) { activeTool = null; currentPoints = []; document.getElementById('btn-group-cursor').classList.add('active'); } 
            else { activeTool = toolName; currentPoints = []; let pBtn = document.getElementById('btn-group-' + toolName); if(!pBtn && toolName==='measure') pBtn = document.getElementById('btn-measure'); if(!pBtn && toolName==='hline') pBtn = document.getElementById('btn-group-trend'); if(!pBtn && toolName==='cyclic') pBtn = document.getElementById('btn-group-patterns'); if(pBtn) pBtn.classList.add('active'); if(event && event.currentTarget.classList.contains('flyout-item')) { pBtn.querySelector('.tool-main').innerHTML = event.currentTarget.querySelector('svg').outerHTML; } }
        };

        function distToSegment(px, py, x1, y1, x2, y2) { const A=px-x1, B=py-y1, C=x2-x1, D=y2-y1; const dot=A*C+B*D; const lenSq=C*C+D*D; let param=-1; if(lenSq!==0) param=dot/lenSq; let xx,yy; if(param<0){xx=x1;yy=y1;}else if(param>1){xx=x2;yy=y2;}else{xx=x1+param*C;yy=y1+param*D;} return Math.sqrt((px-xx)**2+(py-yy)**2); }

        const ctxMenu = document.getElementById('context-menu');
        function showContextMenu(x, y) { ctxMenu.style.display = 'flex'; ctxMenu.style.left = (x + 65) + 'px'; ctxMenu.style.top = (y - 50) + 'px'; }
        function hideContextMenu() { ctxMenu.style.display = 'none'; ctxMenu.style.left = '-1000px'; selectedDrawingIndex = -1; document.querySelectorAll('.ctx-dropdown').forEach(d => d.style.display = 'none'); }
        
        window.changeWidth = function(w) { if (selectedDrawingIndex > -1) { drawings[selectedDrawingIndex].width = w; document.getElementById('active-width-label').innerText = w + 'px'; } document.querySelectorAll('.ctx-dropdown').forEach(d => d.style.display = 'none'); }
        window.changeColor = function(c) { if (selectedDrawingIndex > -1) { drawings[selectedDrawingIndex].color = c; document.getElementById('active-color-dot').style.background = c; } document.querySelectorAll('.ctx-dropdown').forEach(d => d.style.display = 'none'); }
        window.changeStyle = function(s) { if (selectedDrawingIndex > -1) drawings[selectedDrawingIndex].style = s; document.querySelectorAll('.ctx-dropdown').forEach(d => d.style.display = 'none'); }
        window.deleteSelectedDrawing = function() { if (selectedDrawingIndex > -1) drawings.splice(selectedDrawingIndex, 1); hideContextMenu(); }

        chart.subscribeCrosshairMove((param) => {
            if (param.point && param.time) { 
                crosshairLog = chart.timeScale().coordinateToLogical(param.point.x); crosshairPrice = series.coordinateToPrice(param.point.y); 
                const dataPoint = chartData.find(d => d.time === param.time); const prevPoint = chartData[chartData.indexOf(dataPoint) - 1] || dataPoint;
                if (dataPoint) { document.getElementById('leg-o').innerText = dataPoint.open.toFixed(2); document.getElementById('leg-h').innerText = dataPoint.high.toFixed(2); document.getElementById('leg-l').innerText = dataPoint.low.toFixed(2); document.getElementById('leg-c').innerText = dataPoint.close.toFixed(2); const diff = dataPoint.close - prevPoint.close; const pct = (diff / prevPoint.close) * 100; const sign = diff >= 0 ? '+' : ''; const chgEl = document.getElementById('leg-chg'); chgEl.innerText = `${sign}${diff.toFixed(2)} (${sign}${pct.toFixed(2)}%)`; chgEl.className = diff >= 0 ? 'leg-up' : 'leg-down'; }
                activeIndicators.forEach(ind => { if (ind.legendRow.style.display === 'none') return; ind.series.forEach((s, idx) => { let val = param.seriesData.get(s); let el = document.getElementById(`ind-val-${ind.id}-${idx}`); if (el) el.innerText = (val && val.value !== undefined) ? val.value.toFixed(2) : '-'; }); });
            } else { crosshairLog = null; crosshairPrice = null; }
        });

        chart.subscribeClick((param) => {
            if (!param.point || isGlobalLocked) return; const px = param.point.x; const py = param.point.y;
            if (activeTool === null) {
                let hitIndex = -1;
                for (let i = drawings.length - 1; i >= 0; i--) {
                    const d = drawings[i];
                    if (d.type === 'hline') { const y = series.priceToCoordinate(d.price); if (y !== null && Math.abs(py - y) < 8) { hitIndex = i; break; }
                    } else if (d.type === 'trend' && d.p1 && d.p2) { const x1=chart.timeScale().logicalToCoordinate(d.p1.logical); const y1=series.priceToCoordinate(d.p1.price); const x2=chart.timeScale().logicalToCoordinate(d.p2.logical); const y2=series.priceToCoordinate(d.p2.price); if (x1!==null && y1!==null && x2!==null && y2!==null) { if (distToSegment(px,py,x1,y1,x2,y2)<8) { hitIndex=i; break; } }
                    } else if (d.type === 'measure' && d.p1 && d.p2) { const x1=chart.timeScale().logicalToCoordinate(d.p1.logical); const y1=series.priceToCoordinate(d.p1.price); const x2=chart.timeScale().logicalToCoordinate(d.p2.logical); const y2=series.priceToCoordinate(d.p2.price); if (x1!==null && y1!==null && x2!==null && y2!==null) { if (px>=Math.min(x1,x2) && px<=Math.max(x1,x2) && py>=Math.min(y1,y2) && py<=Math.max(y1,y2)) { hitIndex=i; break; } }
                    } else if (d.type === 'fib' && d.p1 && d.p2) { const y1=series.priceToCoordinate(d.p1.price); const y2=series.priceToCoordinate(d.p2.price); const minY=Math.min(y1,y2); const maxY=Math.max(y1,y2); if (py>=minY-10 && py<=maxY+10) { hitIndex=i; break; }
                    } else if (d.type === 'cyclic' && d.interval > 0) { const range = chart.timeScale().getVisibleLogicalRange(); if (range) { let curLog=d.start; while(curLog >= range.from - d.interval) curLog -= d.interval; while(curLog <= range.to + d.interval) { const x = chart.timeScale().logicalToCoordinate(curLog); if (x!==null && Math.abs(px-x)<8) { hitIndex=i; break; } curLog+=d.interval; } } if(hitIndex!==-1) break; }
                }
                if (hitIndex !== -1) { selectedDrawingIndex = hitIndex; document.getElementById('active-color-dot').style.background = drawings[hitIndex].color || '#2962FF'; document.getElementById('active-width-label').innerText = (drawings[hitIndex].width || 2) + 'px'; document.getElementById('ctx-btn-lock').style.color = drawings[hitIndex].isLocked ? '#2962FF' : (document.body.classList.contains('light-theme') ? '#131722' : '#d1d4dc'); showContextMenu(px, py); } else { hideContextMenu(); }
                return;
            }

            const logical = chart.timeScale().coordinateToLogical(px); const price = series.coordinateToPrice(py);
            if (logical === null || price === null) return;
            currentPoints.push({ logical, price });
            
            const defColor = '#2962FF'; const defWidth = 2; const defStyle = 'solid';
            if (activeTool === 'hline') { const newDraw = { type: 'hline', price: price, color: defColor, width: defWidth, style: defStyle, isLocked: false }; drawings.push(newDraw); actionHistory.push({ type: 'DRAWING_ADD', payload: newDraw }); redoHistory = []; currentPoints = []; setTool(null); 
            } else if (currentPoints.length === 2) {
                let newDraw = null;
                if (activeTool === 'trend') newDraw = { type: 'trend', p1: currentPoints[0], p2: currentPoints[1], color: defColor, width: defWidth, style: defStyle, isLocked: false };
                if (activeTool === 'fib') newDraw = { type: 'fib', p1: currentPoints[0], p2: currentPoints[1], color: defColor, width: defWidth, style: defStyle, isLocked: false };
                if (activeTool === 'measure') newDraw = { type: 'measure', p1: currentPoints[0], p2: currentPoints[1], isLocked: false };
                if (activeTool === 'cyclic') { const diff = Math.abs(currentPoints[1].logical - currentPoints[0].logical); if (diff > 0) newDraw = { type: 'cyclic', start: Math.min(currentPoints[0].logical, currentPoints[1].logical), interval: diff, color: '#f59e0b', width: defWidth, style: defStyle, isLocked: false }; }
                if(newDraw) { drawings.push(newDraw); actionHistory.push({ type: 'DRAWING_ADD', payload: newDraw }); redoHistory = []; } currentPoints = []; setTool(null); 
            }
        });

        function renderDrawings() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (sessionActive) { ctx.beginPath(); ctx.strokeStyle = sColors[sessionColorIdx]; ctx.lineWidth = 1; if(sStyles[sessionStyleIdx] === 'dashed') ctx.setLineDash([4, 4]); else if(sStyles[sessionStyleIdx] === 'dotted') ctx.setLineDash([2, 4]); else ctx.setLineDash([]); sessionBreakPoints.forEach(t => { const coord = chart.timeScale().timeToCoordinate(t); if (coord !== null && coord >= 0 && coord <= canvas.width) { ctx.moveTo(coord, 0); ctx.lineTo(coord, canvas.height); } }); ctx.stroke(); ctx.setLineDash([]); }
            
            // --- NEW: PERFECT TRADE DRAWINGS DIRECTLY ON CANVAS ---
            if (isStrategyVisible && strategyTrades && strategyTrades.length > 0) { 
                strategyTrades.forEach(trade => { 
                    const x1 = chart.timeScale().timeToCoordinate(trade.entry_time); 
                    const x2 = chart.timeScale().timeToCoordinate(trade.exit_time) || canvas.width; 
                    const yEntry = series.priceToCoordinate(trade.entry); 
                    const yExit = series.priceToCoordinate(trade.exit); 
                    
                    if (x1 !== null && yEntry !== null) { 
                        // Vertical Purple Line
                        ctx.beginPath(); ctx.strokeStyle = '#9333ea'; ctx.lineWidth = 2; ctx.moveTo(x1, 0); ctx.lineTo(x1, canvas.height); ctx.stroke(); 
                        
                        // "CD" Text (Orange)
                        ctx.fillStyle = '#f59e0b'; ctx.font = 'bold 12px sans-serif'; ctx.fillText('CD', x1 - 8, yEntry - 10); 
                        
                        if (x2 !== null && yExit !== null) { 
                            // Horizontal Blue Lines (Entry and Exit bounds)
                            ctx.beginPath(); ctx.strokeStyle = '#2962FF'; ctx.lineWidth = 2; 
                            ctx.moveTo(x1, yEntry); ctx.lineTo(x2, yEntry); 
                            ctx.moveTo(x1, yExit); ctx.lineTo(x2, yExit); 
                            ctx.stroke(); 
                            
                            // "TP +60.0" or "SL -X.X" Text
                            let pnlText = (trade.pnl >= 0 ? 'TP +' : 'SL ') + trade.pnl.toFixed(1); 
                            ctx.fillStyle = trade.pnl >= 0 ? '#26a69a' : '#ef5350'; 
                            ctx.font = '12px sans-serif'; 
                            ctx.fillText(pnlText, x1 + 4, yExit + (trade.pnl >= 0 ? 14 : -6)); 
                        } 
                    } 
                }); 
            }
            
            drawings.forEach((d, i) => drawShape(d, false, i === selectedDrawingIndex));
            if (currentPoints.length === 1 && crosshairLog !== null && crosshairPrice !== null && !isGlobalLocked) { drawShape({ type: activeTool, p1: currentPoints[0], p2: { logical: crosshairLog, price: crosshairPrice }, price: currentPoints[0].price, logical: currentPoints[0].logical, start: currentPoints[0].logical, interval: Math.abs(crosshairLog - currentPoints[0].logical), color: '#2962FF', width: 2, style: activeTool === 'measure' ? 'solid' : 'dashed' }, true); }
            requestAnimationFrame(renderDrawings);
        }
        
        function drawShape(d, isPreview = false, isSelected = false) {
            ctx.globalAlpha = isPreview ? 0.6 : 1.0; const cColor = d.color || '#2962FF'; const cWidth = d.width || 2; const cStyle = d.style || 'solid'; const itemLocked = d.isLocked || isGlobalLocked;
            if (isSelected && d.type !== 'measure' && !itemLocked) { ctx.shadowColor = '#ffffff'; ctx.shadowBlur = 8; } else { ctx.shadowBlur = 0; }
            if(cStyle === 'dashed') ctx.setLineDash([6, 6]); else if(cStyle === 'dotted') ctx.setLineDash([2, 4]); else ctx.setLineDash([]);
            if (d.type === 'hline') { const y = series.priceToCoordinate(d.price); if (y !== null) { ctx.beginPath(); ctx.strokeStyle = cColor; ctx.lineWidth = cWidth; ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke(); } }
            if (d.type === 'trend' && d.p1 && d.p2) { const x1 = chart.timeScale().logicalToCoordinate(d.p1.logical); const y1 = series.priceToCoordinate(d.p1.price); const x2 = chart.timeScale().logicalToCoordinate(d.p2.logical); const y2 = series.priceToCoordinate(d.p2.price); if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) { ctx.beginPath(); ctx.strokeStyle = cColor; ctx.lineWidth = cWidth; ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); if ((isSelected || isPreview) && !itemLocked) { ctx.setLineDash([]); ctx.fillStyle = '#ffffff'; ctx.strokeStyle = cColor; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x1, y1, 4, 0, 2*Math.PI); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.arc(x2, y2, 4, 0, 2*Math.PI); ctx.fill(); ctx.stroke(); } } }
            if (d.type === 'cyclic' && d.interval > 0) { const range = chart.timeScale().getVisibleLogicalRange(); if (range) { ctx.strokeStyle = cColor; ctx.lineWidth = cWidth; let curLog = d.start; while(curLog >= range.from - d.interval) curLog -= d.interval; while(curLog <= range.to + d.interval) { const x = chart.timeScale().logicalToCoordinate(curLog); if (x !== null) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke(); } curLog += d.interval; } } }
            ctx.setLineDash([]); 
            if (d.type === 'measure' && d.p1 && d.p2) {
                const x1 = chart.timeScale().logicalToCoordinate(d.p1.logical); const y1 = series.priceToCoordinate(d.p1.price); const x2 = chart.timeScale().logicalToCoordinate(d.p2.logical); const y2 = series.priceToCoordinate(d.p2.price);
                if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
                    const minX = Math.min(x1, x2); const minY = Math.min(y1, y2); const w = Math.abs(x2 - x1); const h = Math.abs(y2 - y1);
                    const isUp = d.p2.price >= d.p1.price; const borderC = isUp ? '#26a69a' : '#ef5350'; const fillC = isUp ? 'rgba(38, 166, 154, 0.3)' : 'rgba(239, 83, 80, 0.3)';
                    ctx.fillStyle = fillC; ctx.fillRect(minX, minY, w, h); ctx.strokeStyle = fillC; ctx.lineWidth = 1; ctx.strokeRect(minX, minY, w, h);
                    ctx.beginPath(); ctx.moveTo(minX, y2); ctx.lineTo(minX + w, y2); ctx.stroke(); ctx.beginPath(); ctx.moveTo(x2, minY); ctx.lineTo(x2, minY + h); ctx.stroke();
                    const diff = d.p2.price - d.p1.price; const pct = (diff / d.p1.price) * 100; const ticks = Math.round(diff / 0.05); const sign = diff >= 0 ? '+' : '';
                    const bars = Math.round(Math.abs(d.p2.logical - d.p1.logical)); const days = Math.floor(bars / 375); const hours = Math.floor((bars % 375) / 60); const mins = bars % 60;
                    let timeStr = `${bars}m`; if (days > 0) timeStr = `${days}d ${hours}h`; else if (hours > 0) timeStr = `${hours}h ${mins}m`;
                    const startIdx = Math.max(0, Math.round(Math.min(d.p1.logical, d.p2.logical))); const endIdx = Math.min(chartData.length - 1, Math.round(Math.max(d.p1.logical, d.p2.logical)));
                    let totalVol = 0; for(let i = startIdx; i <= endIdx; i++) { if(chartData[i]) totalVol += chartData[i].volume; }
                    let volText = (totalVol > 1000000) ? (totalVol / 1000000).toFixed(2) + 'M' : (totalVol > 1000) ? (totalVol / 1000).toFixed(2) + 'K' : totalVol.toFixed(0);
                    const textLines = [`${sign}${diff.toFixed(2)} (${sign}${pct.toFixed(2)}%) ${sign}${ticks}`, `${bars} bars, ${timeStr}`, `Vol ${volText}`];
                    ctx.font = '13px -apple-system, sans-serif'; const maxTextW = Math.max(...textLines.map(t => ctx.measureText(t).width)) + 30;
                    const tooltipY = Math.max(y1, y2) + 15; const centerX = minX + (w / 2); const tipX = centerX - (maxTextW/2);
                    ctx.fillStyle = borderC; ctx.beginPath(); ctx.roundRect(tipX, tooltipY, maxTextW, 70, 6); ctx.fill();
                    ctx.fillStyle = '#ffffff'; ctx.textAlign = 'center'; ctx.fillText(textLines[0], centerX, tooltipY + 22); ctx.fillText(textLines[1], centerX, tooltipY + 42); ctx.fillText(textLines[2], centerX, tooltipY + 62); ctx.textAlign = 'left';
                }
            }
            ctx.shadowBlur = 0; ctx.globalAlpha = 1.0;
        }
        
        // --- 4. MONACO INITIALIZATION ---
        let monacoEditor = null;
        require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.39.0/min/vs' }});
        
        window.MonacoEnvironment = {
            getWorkerUrl: function(workerId, label) {
                return "data:text/javascript;charset=utf-8," + encodeURIComponent(
                    "self.MonacoEnvironment = { baseUrl: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.39.0/min/' };\\n" +
                    "importScripts('https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.39.0/min/vs/base/worker/workerMain.js');"
                );
            }
        };

        window.openPineEditor = function() {
            document.getElementById('pine-editor-overlay').style.display = 'flex';
            if (!monacoEditor) {
                require(['vs/editor/editor.main'], function() {
                    monacoEditor = monaco.editor.create(document.getElementById('monaco-overlay-container'), {
                        value: `//@version=6\\nstrategy("BANKNIFTY Direct CD Simple", overlay=true, initial_capital=100000)\\n\\n// Paste your strategy here...`,
                        language: 'python',
                        theme: 'vs-dark',
                        automaticLayout: true,
                        minimap: { enabled: false },
                        fontSize: 14
                    });
                });
            }
        };

        // --- 5. EXECUTION & ROBUST SERVER BRIDGE ---
        async function executePineScript() {
            const btn = document.getElementById('run-pine-btn');
            btn.innerText = "Running...";
            btn.disabled = true;
            
            try {
                const response = await fetch('/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: monacoEditor.getValue() })
                });
                
                const rawText = await response.text();
                let data;
                try {
                    data = JSON.parse(rawText);
                } catch(e) {
                    alert("NODE ENGINE CRASH:\\nRemove any input() or input.time() boxes from your Pine script. The local headless engine requires hardcoded numeric variables.\\n\\nRaw Error Output:\\n" + rawText.substring(0, 500));
                    btn.innerText = "Run Script";
                    btn.disabled = false;
                    return;
                }
                
                if (data.success && data.strategy) {
                    try {
                        document.getElementById('pine-editor-overlay').style.display = 'none';
                        
                        const strat = data.strategy;
                        const w = strat.wintrades || 0;
                        const l = strat.losstrades || 0;
                        const totalTrades = w + l;
                        const winrate = totalTrades > 0 ? ((w/totalTrades)*100).toFixed(2) : "0.00";
                        const np = strat.netprofit || 0;
                        const pf = strat.grossloss > 0 ? (strat.grossprofit / strat.grossloss).toFixed(2) : "0.00";
                        const dd = strat.max_drawdown || 0;
                        
                        const pnlEl = document.getElementById('metric-pnl');
                        if (pnlEl) {
                            pnlEl.innerText = np >= 0 ? '+' + np.toFixed(2) : np.toFixed(2);
                            pnlEl.className = 'st-metric-val ' + (np >= 0 ? 'val-up' : 'val-down');
                        }
                        
                        const trdsEl = document.getElementById('metric-trades');
                        if (trdsEl) trdsEl.innerText = totalTrades;
                        
                        const wrEl = document.getElementById('metric-winrate');
                        if (wrEl) wrEl.innerText = winrate + '%';
                        
                        const pfEl = document.getElementById('metric-pf');
                        if (pfEl) pfEl.innerText = pf;
                        
                        const ddEl = document.getElementById('metric-dd');
                        if (ddEl) {
                            ddEl.innerText = dd.toFixed(2);
                            ddEl.className = 'st-metric-val ' + (dd > 0 ? 'val-down' : 'val-neutral');
                        }

                        if (data.strategy_trades && Array.isArray(data.strategy_trades)) {
                            let runEq = 100000;
                            let rawMarkers = [];
                            
                            const timeArray = chartData.map(d => d.time);
                            const validTimes = new Set(timeArray);

                            function snapToCandle(tSec) {
                                if (validTimes.has(tSec)) return tSec;
                                if (!tSec || tSec === 0) return timeArray[0];
                                let closest = timeArray[0];
                                let minDiff = Math.abs(tSec - closest);
                                for(let i=1; i<timeArray.length; i++) {
                                    let diff = Math.abs(tSec - timeArray[i]);
                                    if(diff < minDiff) { minDiff = diff; closest = timeArray[i]; }
                                }
                                return closest;
                            }

                            strategyTrades = data.strategy_trades.map(t => {
                                let pnl = t.profit !== undefined ? t.profit : (t.pnl !== undefined ? t.pnl : 0);
                                runEq += pnl;
                                
                                let eTimeVal = t.entryTime || t.entry_time || (t.entry && t.entry.time) || t.time || 0;
                                let xTimeVal = t.exitTime || t.exit_time || (t.exit && t.exit.time) || 0;
                                
                                let eTimeMs = typeof eTimeVal === 'string' ? new Date(eTimeVal).getTime() : eTimeVal;
                                let xTimeMs = typeof xTimeVal === 'string' ? new Date(xTimeVal).getTime() : xTimeVal;
                                
                                let eTime = eTimeMs > 10000000000 ? Math.floor(eTimeMs / 1000) : eTimeMs;
                                let xTime = xTimeMs > 10000000000 ? Math.floor(xTimeMs / 1000) : xTimeMs;
                                
                                let direction = t.direction || (t.side && t.side.toLowerCase() === 'long' ? 'long' : 'short');
                                
                                let validE = snapToCandle(eTime);
                                if (validE) {
                                    rawMarkers.push({
                                        time: validE,
                                        position: direction === 'long' ? 'belowBar' : 'aboveBar',
                                        color: direction === 'long' ? '#2962FF' : '#ef5350',
                                        shape: direction === 'long' ? 'arrowUp' : 'arrowDown',
                                        text: '' // Note: The Text 'CD' is drawn beautifully by the canvas above
                                    });
                                }
                                
                                let validX = snapToCandle(xTime);
                                if (xTimeVal && validX) {
                                    rawMarkers.push({
                                        time: validX,
                                        position: direction === 'long' ? 'aboveBar' : 'belowBar',
                                        color: pnl >= 0 ? '#26a69a' : '#ef5350',
                                        shape: direction === 'long' ? 'arrowDown' : 'arrowUp',
                                        text: '' 
                                    });
                                }

                                return {
                                    side: direction === 'long' ? 'Long' : 'Short',
                                    entry_time: validE,
                                    exit_time: validX,
                                    entry: t.entryPrice || (t.entry && t.entry.price) || 0,
                                    exit: t.exitPrice || (t.exit && t.exit.price) || 0,
                                    pnl: pnl,
                                    equity: runEq
                                };
                            });
                            
                            rawMarkers.sort((a, b) => a.time - b.time);
                            strategyMarkers = [];
                            let seenTimes = new Map();
                            
                            for(let i=0; i<rawMarkers.length; i++) {
                                let m = rawMarkers[i];
                                if(seenTimes.has(m.time)) {
                                    let existing = seenTimes.get(m.time);
                                    if (m.text.includes('TP') || m.text.includes('SL')) {
                                        existing.color = m.color;
                                    }
                                } else {
                                    let mClone = { ...m };
                                    seenTimes.set(m.time, mClone);
                                    strategyMarkers.push(mClone);
                                }
                            }
                            
                            series.setMarkers(strategyMarkers.filter(m => m.time != null));
                            renderTradeList();
                        }
                        
                        let pineScript = monacoEditor.getValue();
                        let strategyNameMatch = pineScript.match(/strategy\(['"]([^'"]+)['"]/);
                        let stratName = strategyNameMatch ? strategyNameMatch[1] : "Pine Script Strategy";
                        
                        const legTitle = document.getElementById('legend-strategy-title');
                        if (legTitle) legTitle.innerText = stratName;
                        
                        const panTitle = document.getElementById('panel-strategy-title');
                        if (panTitle) panTitle.innerText = stratName;

                        const leg = document.getElementById('strategy-legend');
                        if (leg) leg.style.display = 'flex';
                        
                        const tester = document.getElementById('strategy-tester');
                        if (tester) tester.style.display = 'flex';
                        
                        isStrategyVisible = true;
                        
                        const eye = document.getElementById('eye-icon');
                        if (eye) eye.style.opacity = '1';
                        
                        requestAnimationFrame(renderDrawings);
                    } catch (domErr) {
                        console.error("DOM Update Failed:", domErr);
                    }
                } else {
                    alert('PineTS Compilation Error:\\n' + (data.error || 'Failed to extract strategy metrics.'));
                }
            } catch (err) {
                alert("Connection to backend failed. Make sure backtest.py is running.\\n" + err.message);
            } finally {
                btn.innerText = "Run Script";
                btn.disabled = false;
            }
        }
    </script>
</body>
</html>
"""

html_content = html_template.replace('__CHART_DATA__', json_data)
html_content = html_content.replace('__STRATEGY_MARKERS__', json_markers)
html_content = html_content.replace('__CYCLE_LINES__', json_cycles)
html_content = html_content.replace('__TRADE_DATA__', json_trades)
html_content = html_content.replace('__STRATEGY_STATS__', json_stats)

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

print("Engine Output Generated. BANKNIFTY data and candlestick rendering confirmed.")

# ==========================================
# 6. HTTP SERVER BRIDGE (Live Connection)
# ==========================================
class PineLabHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/dashboard.html'
        return super().do_GET()

    def do_POST(self):
        if self.path == '/run':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                code = json.loads(post_data).get('code', '')
                with open('strategy.pine', 'w') as f:
                    f.write(code)
                
                process = subprocess.run(['node', 'engine.mjs'], capture_output=True, text=True)
                
                output = process.stdout if process.stdout else process.stderr
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(output.encode('utf-8'))
            except Exception as e:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

if __name__ == '__main__':
    print("==========================================")
    print(" 🚀 BANKNIFTY QUANT LAB IS LIVE ")
    print(" Open your browser to: http://localhost:8080")
    print("==========================================")
    HTTPServer(('localhost', 8080), PineLabHandler).serve_forever()