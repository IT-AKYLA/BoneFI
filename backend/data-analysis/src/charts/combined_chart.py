# data-analysis/src/charts/combined_chart.py
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
import base64
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

plt.style.use('dark_background')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Segoe UI', 'DejaVu Sans']
plt.rcParams['figure.facecolor'] = '#0a0c10'
plt.rcParams['axes.facecolor'] = '#0f1117'
plt.rcParams['axes.edgecolor'] = '#2a2e3a'
plt.rcParams['grid.color'] = '#2a2e3a'
plt.rcParams['grid.alpha'] = 0.3
plt.rcParams['text.color'] = '#e4e6eb'


class CombinedChartGenerator:
    
    def __init__(self):
        self.colors = {
            'transactions': '#4e79a7',
            'buy': '#2ecc71',
            'sell': '#e74c3c',
            'migration': '#ff8c00',
            'grid': '#2a2e3a',
            'background': '#0f1117',
            'text': '#e4e6eb'
        }
    
    def extract_combined_data(self, analyzer, token_mint: str, 
                               exclude_pools: bool = True, 
                               interval_minutes: int = 5,
                               migration_time: Optional[datetime] = None) -> pd.DataFrame:
        
        transactions = analyzer.transactions
        if not transactions:
            return pd.DataFrame()
        
        total_supply = analyzer.total_supply if analyzer.total_supply > 0 else 1_000_000_000
        
        timestamps = [tx.get("blockTime", 0) for tx in transactions if tx.get("blockTime", 0) > 0]
        if not timestamps:
            return pd.DataFrame()
        
        min_time = datetime.fromtimestamp(min(timestamps))
        max_time = datetime.fromtimestamp(max(timestamps))
        
        pool_addresses = set()
        if exclude_pools and hasattr(analyzer, 'current_holders'):
            total_balance = sum(analyzer.current_holders.values()) if analyzer.current_holders else 0
            for addr, balance in analyzer.current_holders.items():
                share = (balance / total_balance * 100) if total_balance > 0 else 0
                tx_count = analyzer.address_activity.get(addr, 0)
                if hasattr(analyzer, 'is_liquidity_pool') and analyzer.is_liquidity_pool(addr, share, tx_count):
                    pool_addresses.add(addr)
        
        tx_data = defaultdict(int)
        buy_data = defaultdict(float)
        sell_data = defaultdict(float)
        
        processed_txs = set()
        
        for tx in transactions:
            tx_sig = tx.get("transaction", {}).get("signatures", [""])[0]
            if tx_sig in processed_txs:
                continue
            processed_txs.add(tx_sig)
            
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0:
                continue
            
            dt = datetime.fromtimestamp(timestamp)
            
            interval_key = dt.replace(
                minute=(dt.minute // interval_minutes) * interval_minutes,
                second=0, microsecond=0
            )
            
            tx_data[interval_key] += 1
            
            tx_meta = tx.get("meta", {})
            pre_balances = tx_meta.get("preTokenBalances", [])
            post_balances = tx_meta.get("postTokenBalances", [])
            
            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]
            
            has_pool = any(addr in pool_addresses for addr in account_keys)
            
            if not has_pool:
                continue
            
            total_change = 0
            
            for bal in pre_balances:
                if bal.get('mint') == token_mint:
                    owner = bal.get('owner', '')
                    amount = int(bal.get('uiTokenAmount', {}).get('amount', 0))
                    if owner and owner not in pool_addresses:
                        total_change -= amount
            
            for bal in post_balances:
                if bal.get('mint') == token_mint:
                    owner = bal.get('owner', '')
                    amount = int(bal.get('uiTokenAmount', {}).get('amount', 0))
                    if owner and owner not in pool_addresses:
                        total_change += amount
            
            if total_change != 0:
                volume_percent = (abs(total_change) / total_supply * 100) if total_supply > 0 else 0
                if volume_percent > 0 and volume_percent < 1000:
                    if total_change > 0:
                        buy_data[interval_key] += volume_percent
                    else:
                        sell_data[interval_key] += volume_percent
        
        all_intervals = []
        current = min_time.replace(minute=0, second=0, microsecond=0)
        while current <= max_time:
            rounded = current.replace(
                minute=(current.minute // interval_minutes) * interval_minutes,
                second=0, microsecond=0
            )
            if rounded not in all_intervals:
                all_intervals.append(rounded)
            current += timedelta(minutes=interval_minutes)
        
        all_intervals = sorted(all_intervals)
        
        df = pd.DataFrame({'timestamp': all_intervals})
        df['transactions'] = df['timestamp'].apply(lambda x: tx_data.get(x, 0))
        df['buy_volume'] = df['timestamp'].apply(lambda x: buy_data.get(x, 0))
        df['sell_volume'] = df['timestamp'].apply(lambda x: sell_data.get(x, 0))
        df['time_str'] = df['timestamp'].dt.strftime('%m-%d %H:%M')
        
        return df
    
    def detect_pattern(self, df: pd.DataFrame, migration_time: Optional[datetime]) -> Dict:
        if df.empty:
            return {"pattern": "NO_DATA", "description": "Нет данных"}
        
        if migration_time:
            pre_df = df[df['timestamp'] < migration_time]
            post_df = df[df['timestamp'] >= migration_time]
            
            pre_tx_avg = pre_df['transactions'].mean() if not pre_df.empty else 0
            post_tx_avg = post_df['transactions'].mean() if not post_df.empty else 0
            pre_buy_avg = pre_df['buy_volume'].mean() if not pre_df.empty else 0
            post_buy_avg = post_df['buy_volume'].mean() if not post_df.empty else 0
            
            if post_tx_avg < pre_tx_avg * 0.3:
                pattern = "POST_MIGRATION_COLLAPSE"
                description = "Резкий спад активности после миграции"
            elif pre_tx_avg > 50 and post_buy_avg < pre_buy_avg * 0.5:
                pattern = "PRE_MIGRATION_PUMP"
                description = "Искусственный пампинг перед миграцией"
            elif post_buy_avg > pre_buy_avg * 2:
                pattern = "POST_MIGRATION_ACCUMULATION"
                description = "Активное накопление после миграции"
            else:
                pattern = "NORMAL"
                description = "Нормальная активность"
        else:
            pattern = "NOT_MIGRATED"
            description = "Токен не мигрировал"
        
        return {"pattern": pattern, "description": description}
    
    def generate_chart(self, df: pd.DataFrame, token_name: str, 
                       migration_time: Optional[datetime] = None,
                       interval_minutes: int = 5) -> Tuple[plt.Figure, plt.Axes]:
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), 
                                         facecolor=self.colors['background'],
                                         gridspec_kw={'height_ratios': [1, 1]})
        
        if df.empty:
            for ax in [ax1, ax2]:
                ax.text(0.5, 0.5, 'No data available', ha='center', va='center', 
                       fontsize=14, color=self.colors['text'])
                ax.set_facecolor(self.colors['background'])
            return fig, (ax1, ax2)
        
        x = df['timestamp']
        
        ax1.set_facecolor(self.colors['background'])
        ax1.plot(x, df['transactions'].values, color=self.colors['transactions'], 
                linewidth=2.5, marker='o', markersize=3, label='Transactions', zorder=3)
        ax1.fill_between(x, 0, df['transactions'].values, 
                         color=self.colors['transactions'], alpha=0.15, zorder=1)
        
        if migration_time:
            ax1.axvline(x=migration_time, color=self.colors['migration'], 
                       linestyle='--', linewidth=2.5, alpha=0.9, 
                       label='Migration', zorder=5)
        
        ax1.set_ylabel('Transactions', fontsize=11, fontweight='bold')
        ax1.set_title(f'📊 {token_name[:30]}... - Activity & Volume ({interval_minutes} min intervals)', 
                     fontsize=12, fontweight='bold', pad=15)
        ax1.legend(loc='upper left', frameon=True, facecolor='#1a1d24', edgecolor='#2a2e3a')
        ax1.grid(True, alpha=0.2, linestyle='--')
        
        ax2.set_facecolor(self.colors['background'])
        ax2.plot(x, df['buy_volume'].values, color=self.colors['buy'], 
                linewidth=2.5, marker='o', markersize=3, label='Buy Volume (% of supply)', zorder=3)
        ax2.plot(x, df['sell_volume'].values, color=self.colors['sell'], 
                linewidth=2.5, marker='s', markersize=3, label='Sell Volume (% of supply)', zorder=3)
        ax2.fill_between(x, 0, df['buy_volume'].values, color=self.colors['buy'], alpha=0.15, zorder=1)
        ax2.fill_between(x, 0, df['sell_volume'].values, color=self.colors['sell'], alpha=0.15, zorder=1)
        
        if migration_time:
            ax2.axvline(x=migration_time, color=self.colors['migration'], 
                       linestyle='--', linewidth=2.5, alpha=0.9, 
                       label='Migration', zorder=5)
        
        ax2.set_xlabel('Time', fontsize=11, fontweight='bold')
        ax2.set_ylabel('Volume (% of supply)', fontsize=11, fontweight='bold')
        ax2.legend(loc='upper left', frameon=True, facecolor='#1a1d24', edgecolor='#2a2e3a')
        ax2.grid(True, alpha=0.2, linestyle='--')
        
        for ax in [ax1, ax2]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right', fontsize=8)
        
        plt.tight_layout()
        return fig, (ax1, ax2)
    
    def generate_base64(self, df: pd.DataFrame, token_mint: str, 
                       migration_time: Optional[datetime] = None,
                       interval_minutes: int = 5) -> str:
        fig, _ = self.generate_chart(df, token_mint, migration_time, interval_minutes)
        
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=120, bbox_inches='tight', 
                   facecolor=self.colors['background'])
        buf.seek(0)
        
        img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)
        
        return img_base64
    
    def get_chart_data(self, analyzer, token_mint: str, 
                       exclude_pools: bool = True, 
                       interval_minutes: int = 5) -> Dict:
        
        migration_time = None
        if hasattr(analyzer, 'migration_time') and analyzer.migration_time:
            if isinstance(analyzer.migration_time, (int, float)):
                migration_time = datetime.fromtimestamp(analyzer.migration_time)
            else:
                migration_time = analyzer.migration_time
        
        df = self.extract_combined_data(analyzer, token_mint, exclude_pools, 
                                         interval_minutes, migration_time)
        
        if df.empty:
            return {"error": "No data"}
        
        pattern_info = self.detect_pattern(df, migration_time)
        
        img_base64 = self.generate_base64(df, token_mint, migration_time, interval_minutes)
        
        return {
            "chart_base64": img_base64,
            "interval_minutes": interval_minutes,
            "total_transactions": int(df['transactions'].sum()),
            "total_buy_volume": round(df['buy_volume'].sum(), 2),
            "total_sell_volume": round(df['sell_volume'].sum(), 2),
            "peak_transactions": int(df['transactions'].max()),
            "peak_buy_volume": round(df['buy_volume'].max(), 2),
            "peak_sell_volume": round(df['sell_volume'].max(), 2),
            "pattern": pattern_info["pattern"],
            "pattern_description": pattern_info["description"],
            "migration_time": migration_time.strftime("%Y-%m-%d %H:%M:%S") if migration_time else None
        }