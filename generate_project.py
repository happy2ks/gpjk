#!/usr/bin/env python3
"""
自动化脚本 - 生成四市场金融数据 Skills 项目的所有文件
Usage: python3 generate_project.py
"""

import os
import sys

# 项目根目录
PROJECT_ROOT = "skills/multi-market-finance-free"

# 创建目录结构
DIRECTORIES = [
    f"{PROJECT_ROOT}/scripts",
    f"{PROJECT_ROOT}/examples",
]

# 文件内容字典
FILES = {
    f"{PROJECT_ROOT}/scripts/unified_client.py": '''"""
Unified Market Client - 四市场统一客户端
支持美国、香港、台湾、中国四大市场
无需任何 API KEY
"""

import yfinance as yf
import akshare as ak
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class Quote:
    """股票行情数据"""
    market: str
    symbol: str
    name: str
    price: float
    currency: str
    change_pct: float
    volume: int
    timestamp: datetime

class UnifiedMarketClient:
    """四市场统一客户端"""
    
    MARKET_SUFFIXES = {
        "US": "",
        "HK": ".HK",
        "TW": ".TW",
        "CN": ""
    }
    
    def __init__(self):
        """初始化客户端"""
        pass
    
    def get_quote(self, market: str, symbol: str) -> Optional[Quote]:
        """获取实时行情"""
        try:
            formatted_symbol = self._format_symbol(market, symbol)
            
            if market in ['US', 'HK', 'TW']:
                ticker = yf.Ticker(formatted_symbol)
                info = ticker.info
                
                return Quote(
                    market=market,
                    symbol=symbol,
                    name=info.get('longName', ''),
                    price=info.get('currentPrice', 0),
                    currency=info.get('currency', ''),
                    change_pct=info.get('regularMarketChangePercent', 0),
                    volume=info.get('volume', 0),
                    timestamp=datetime.now()
                )
            elif market == 'CN':
                df = ak.stock_zh_a_spot()
                stock_data = df[df['代码'] == symbol]
                if not stock_data.empty:
                    row = stock_data.iloc[0]
                    return Quote(
                        market=market,
                        symbol=symbol,
                        name=row['名称'],
                        price=float(row['最新价']),
                        currency='CNY',
                        change_pct=float(row['涨跌幅']),
                        volume=int(row['成交量']),
                        timestamp=datetime.now()
                    )
        except Exception as e:
            print(f"Error fetching quote for {symbol}: {e}")
        
        return None
    
    def get_price_history(self, market: str, symbol: str, period: str = "1y") -> List[Dict]:
        """获取历史价格数据"""
        try:
            formatted_symbol = self._format_symbol(market, symbol)
            
            if market in ['US', 'HK', 'TW']:
                ticker = yf.Ticker(formatted_symbol)
                df = ticker.history(period=period)
                
                return [
                    {
                        'date': str(idx.date()),
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'close': float(row['Close']),
                        'volume': int(row['Volume'])
                    }
                    for idx, row in df.iterrows()
                ]
            elif market == 'CN':
                df = ak.stock_zh_a_hist(symbol, period='daily')
                return df.to_dict('records')
        
        except Exception as e:
            print(f"Error fetching history for {symbol}: {e}")
        
        return []
    
    def get_batch_quotes(self, market: str, symbols: List[str]) -> Dict[str, Quote]:
        """批量获取多只股票的行情"""
        results = {}
        for symbol in symbols:
            quote = self.get_quote(market, symbol)
            if quote:
                results[symbol] = quote
        return results
    
    @staticmethod
    def _format_symbol(market: str, symbol: str) -> str:
        """标准化股票代码格式"""
        symbol = symbol.upper()
        suffix = UnifiedMarketClient.MARKET_SUFFIXES.get(market, "")
        
        if suffix and not symbol.endswith(suffix):
            return symbol + suffix
        
        return symbol
''',

    f"{PROJECT_ROOT}/scripts/technical_indicators.py": '''"""
Technical Indicators - 技术指标计算模块
支持 SMA、EMA、RSI、MACD、Bollinger Bands 等指标
"""

import numpy as np
from typing import List, Dict

def calculate_sma(prices: List[float], period: int) -> List[float]:
    """简单移动平均线 (SMA)"""
    sma = []
    for i in range(len(prices)):
        if i < period - 1:
            sma.append(None)
        else:
            avg = sum(prices[i-period+1:i+1]) / period
            sma.append(avg)
    return sma

def calculate_ema(prices: List[float], period: int) -> List[float]:
    """指数移动平均线 (EMA)"""
    ema = []
    k = 2 / (period + 1)
    
    for i, price in enumerate(prices):
        if i == 0:
            ema.append(price)
        else:
            ema.append(price * k + ema[i-1] * (1 - k))
    
    return ema

def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """相对强弱指数 (RSI)"""
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[:period]) / period if period <= len(gains) else 0
    avg_loss = sum(losses[:period]) / period if period <= len(losses) else 0
    
    rsi = []
    for i in range(len(prices)):
        if i < period:
            rsi.append(None)
        else:
            if avg_loss == 0:
                rsi.append(100 if avg_gain > 0 else 0)
            else:
                rs = avg_gain / avg_loss
                rsi.append(100 - (100 / (1 + rs)))
    
    return rsi

def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
    """MACD 指标"""
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    
    macd_line = [ema_fast[i] - ema_slow[i] if ema_fast[i] and ema_slow[i] else None 
                 for i in range(len(prices))]
    
    signal_line = calculate_ema([x for x in macd_line if x is not None], signal)
    
    return {
        'macd': macd_line,
        'signal': signal_line,
        'histogram': [macd_line[i] - signal_line[i-slow+signal] if i >= slow+signal-1 else None 
                      for i in range(len(macd_line))]
    }

def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Dict:
    """布林带"""
    sma = calculate_sma(prices, period)
    
    bands = {'upper': [], 'middle': [], 'lower': []}
    
    for i in range(len(prices)):
        if i < period - 1:
            bands['upper'].append(None)
            bands['middle'].append(None)
            bands['lower'].append(None)
        else:
            std = np.std(prices[i-period+1:i+1])
            middle = sma[i]
            bands['middle'].append(middle)
            bands['upper'].append(middle + std_dev * std)
            bands['lower'].append(middle - std_dev * std)
    
    return bands

def calculate_atr(high: List[float], low: List[float], close: List[float], period: int = 14) -> List[float]:
    """平均真实波幅 (ATR)"""
    tr = []
    for i in range(len(close)):
        if i == 0:
            tr.append(high[i] - low[i])
        else:
            tr1 = high[i] - low[i]
            tr2 = abs(high[i] - close[i-1])
            tr3 = abs(low[i] - close[i-1])
            tr.append(max(tr1, tr2, tr3))
    
    atr = []
    for i in range(len(tr)):
        if i < period - 1:
            atr.append(None)
        else:
            avg = sum(tr[i-period+1:i+1]) / period
            atr.append(avg)
    
    return atr

def calculate_stochastic(high: List[float], low: List[float], close: List[float], 
                        period: int = 14) -> Dict:
    """随机指标"""
    k = []
    
    for i in range(len(close)):
        if i < period - 1:
            k.append(None)
        else:
            lowest = min(low[i-period+1:i+1])
            highest = max(high[i-period+1:i+1])
            
            if highest == lowest:
                k.append(50)
            else:
                k_value = ((close[i] - lowest) / (highest - lowest)) * 100
                k.append(k_value)
    
    d = calculate_sma([x for x in k if x is not None], 3)
    
    return {'k': k, 'd': d}
''',

    f"{PROJECT_ROOT}/scripts/trading_signals.py": '''"""
Trading Signals - 交易信号生成模块
支持 SMA、RSI、MACD、布林带等多种策略
"""

from typing import Dict, List
from .technical_indicators import (
    calculate_sma, calculate_rsi, calculate_macd, calculate_bollinger_bands
)

class TradingSignalGenerator:
    """交易信号生成器"""
    
    def __init__(self):
        pass
    
    def sma_crossover_signal(self, prices: List[float], 
                            fast_period: int = 20, 
                            slow_period: int = 50) -> Dict:
        """SMA 交叉策略信号"""
        sma_fast = calculate_sma(prices, fast_period)
        sma_slow = calculate_sma(prices, slow_period)
        
        signal = 'HOLD'
        confidence = 0.0
        reason = ''
        
        if len(sma_fast) >= 2 and len(sma_slow) >= 2:
            if sma_fast[-2] <= sma_slow[-2] and sma_fast[-1] > sma_slow[-1]:
                signal = 'BUY'
                confidence = 0.85
                reason = f'Golden Cross: SMA({fast_period}) 穿过 SMA({slow_period})'
            elif sma_fast[-2] >= sma_slow[-2] and sma_fast[-1] < sma_slow[-1]:
                signal = 'SELL'
                confidence = 0.85
                reason = f'Death Cross: SMA({fast_period}) 穿过 SMA({slow_period})'
        
        return {
            'signal': signal,
            'confidence': confidence,
            'reason': reason,
            'sma_fast': sma_fast[-1] if sma_fast[-1] else None,
            'sma_slow': sma_slow[-1] if sma_slow[-1] else None
        }
    
    def rsi_extremes_signal(self, prices: List[float], 
                           period: int = 14,
                           overbought: float = 70,
                           oversold: float = 30) -> Dict:
        """RSI 超买超卖策略信号"""
        rsi = calculate_rsi(prices, period)
        
        signal = 'HOLD'
        confidence = 0.0
        reason = ''
        
        if rsi[-1] is not None:
            if rsi[-1] < oversold:
                signal = 'BUY'
                confidence = 0.75
                reason = f'Oversold: RSI({period}) = {rsi[-1]:.2f} < {oversold}'
            elif rsi[-1] > overbought:
                signal = 'SELL'
                confidence = 0.75
                reason = f'Overbought: RSI({period}) = {rsi[-1]:.2f} > {overbought}'
        
        return {
            'signal': signal,
            'confidence': confidence,
            'reason': reason,
            'rsi': rsi[-1]
        }
    
    def macd_signal(self, prices: List[float]) -> Dict:
        """MACD 信号策略"""
        macd_data = calculate_macd(prices)
        
        signal = 'HOLD'
        confidence = 0.0
        reason = ''
        
        macd = macd_data['macd']
        signal_line = macd_data['signal']
        
        if len(macd) >= 2 and len(signal_line) >= 2:
            if macd[-2] <= signal_line[-2] and macd[-1] > signal_line[-1]:
                signal = 'BUY'
                confidence = 0.80
                reason = 'MACD 穿过信号线 (看涨)'
            elif macd[-2] >= signal_line[-2] and macd[-1] < signal_line[-1]:
                signal = 'SELL'
                confidence = 0.80
                reason = 'MACD 穿过信号线 (看跌)'
        
        return {
            'signal': signal,
            'confidence': confidence,
            'reason': reason,
            'macd': macd[-1] if macd[-1] else None,
            'signal_line': signal_line[-1] if signal_line[-1] else None
        }
    
    def bollinger_breakout_signal(self, prices: List[float], 
                                 period: int = 20) -> Dict:
        """布林带突破策略信号"""
        bb = calculate_bollinger_bands(prices, period)
        
        signal = 'HOLD'
        confidence = 0.0
        reason = ''
        
        if bb['upper'][-1] and bb['lower'][-1]:
            if prices[-1] > bb['upper'][-1]:
                signal = 'BUY'
                confidence = 0.70
                reason = f'Price broke above upper band'
            elif prices[-1] < bb['lower'][-1]:
                signal = 'SELL'
                confidence = 0.70
                reason = f'Price broke below lower band'
        
        return {
            'signal': signal,
            'confidence': confidence,
            'reason': reason,
            'price': prices[-1],
            'upper_band': bb['upper'][-1],
            'middle_band': bb['middle'][-1],
            'lower_band': bb['lower'][-1]
        }
    
    def generate_signals(self, prices: List[float], strategy: str = 'all') -> Dict:
        """生成交易信号"""
        signals = {}
        
        if strategy in ['all', 'sma_crossover']:
            signals['sma_crossover'] = self.sma_crossover_signal(prices)
        
        if strategy in ['all', 'rsi']:
            signals['rsi'] = self.rsi_extremes_signal(prices)
        
        if strategy in ['all', 'macd']:
            signals['macd'] = self.macd_signal(prices)
        
        if strategy in ['all', 'bollinger']:
            signals['bollinger'] = self.bollinger_breakout_signal(prices)
        
        return signals
''',

    f"{PROJECT_ROOT}/scripts/portfolio_analyzer.py": '''"""
Portfolio Analyzer - 投资组合分析工具
跟踪持仓、计算损益、分析资产配置
"""

from typing import Dict, List
from datetime import datetime
from .unified_client import UnifiedMarketClient

class PortfolioAnalyzer:
    """投资组合分析工具"""
    
    def __init__(self):
        self.client = UnifiedMarketClient()
        self.holdings = []
    
    def add_holding(self, symbol: str, quantity: float, cost_basis: float, market: str = "US") -> None:
        """添加持仓"""
        self.holdings.append({
            'market': market,
            'symbol': symbol,
            'quantity': quantity,
            'cost_basis': cost_basis,
            'purchase_date': datetime.now()
        })
    
    def remove_holding(self, symbol: str) -> None:
        """移除持仓"""
        self.holdings = [h for h in self.holdings if h['symbol'] != symbol]
    
    def refresh_prices(self) -> None:
        """刷新所有持仓的价格"""
        for holding in self.holdings:
            quote = self.client.get_quote(holding['market'], holding['symbol'])
            if quote:
                holding['current_price'] = quote.price
                holding['current_value'] = quote.price * holding['quantity']
    
    def get_holding_pnl(self, holding: Dict) -> Dict:
        """计算单个持仓的损益"""
        if 'current_price' not in holding:
            self.refresh_prices()
        
        cost = holding['cost_basis'] * holding['quantity']
        current_value = holding.get('current_value', 0)
        gain_loss = current_value - cost
        gain_loss_pct = (gain_loss / cost * 100) if cost != 0 else 0
        
        return {
            'symbol': holding['symbol'],
            'market': holding['market'],
            'quantity': holding['quantity'],
            'cost_basis': holding['cost_basis'],
            'current_price': holding.get('current_price', 0),
            'cost': cost,
            'current_value': current_value,
            'gain_loss': gain_loss,
            'gain_loss_pct': gain_loss_pct
        }
    
    def get_summary_report(self) -> Dict:
        """获取投资组合总结报告"""
        self.refresh_prices()
        
        total_cost = 0
        total_value = 0
        total_gain_loss = 0
        
        holdings_detail = []
        
        for holding in self.holdings:
            pnl = self.get_holding_pnl(holding)
            holdings_detail.append(pnl)
            
            total_cost += pnl['cost']
            total_value += pnl['current_value']
            total_gain_loss += pnl['gain_loss']
        
        total_return_pct = (total_gain_loss / total_cost * 100) if total_cost != 0 else 0
        
        market_allocation = {}
        for holding in holdings_detail:
            market = holding['market']
            if market not in market_allocation:
                market_allocation[market] = 0
            market_allocation[market] += holding['current_value']
        
        return {
            'total_cost': total_cost,
            'total_value': total_value,
            'total_gain_loss': total_gain_loss,
            'total_return_pct': total_return_pct,
            'holdings': holdings_detail,
            'market_allocation': market_allocation,
            'timestamp': datetime.now()
        }
    
    def get_market_allocation(self) -> Dict[str, float]:
        """获取市场配置百分比"""
        report = self.get_summary_report()
        total = report['total_value']
        
        allocation = {}
        for market, value in report['market_allocation'].items():
            allocation[market] = (value / total * 100) if total > 0 else 0
        
        return allocation
''',

    f"{PROJECT_ROOT}/examples/example_basic_queries.py": '''"""
基础查询示例 - 四市场实时行情查询
"""

from scripts.unified_client import UnifiedMarketClient

def main():
    client = UnifiedMarketClient()
    
    print("=" * 70)
    print("四市场无KEY实时行情查询示例")
    print("=" * 70)
    
    # 美国市场
    print("\\n🇺🇸 美国市场")
    print("-" * 70)
    us_stocks = ["AAPL", "MSFT", "GOOGL", "TSLA"]
    us_quotes = client.get_batch_quotes("US", us_stocks)
    for symbol, quote in us_quotes.items():
        print(f"{quote.name:20} ({symbol:6}): ${quote.price:8.2f} {quote.change_pct:+7.2f}%")
    
    # 香港市场
    print("\\n🇭🇰 香港市场")
    print("-" * 70)
    hk_stocks = ["0700", "3690", "1211"]
    hk_quotes = client.get_batch_quotes("HK", hk_stocks)
    for symbol, quote in hk_quotes.items():
        print(f"{quote.name:20} ({symbol:6}): ¥{quote.price:8.2f} {quote.change_pct:+7.2f}%")
    
    # 台湾市场
    print("\\n🇹🇼 台湾市场")
    print("-" * 70)
    tw_stocks = ["2330", "2317"]
    tw_quotes = client.get_batch_quotes("TW", tw_stocks)
    for symbol, quote in tw_quotes.items():
        print(f"{quote.name:20} ({symbol:6}): NT${quote.price:8.2f} {quote.change_pct:+7.2f}%")
    
    # 中国市场
    print("\\n🇨🇳 中国市场")
    print("-" * 70)
    cn_stocks = ["000001", "000858", "600519"]
    cn_quotes = client.get_batch_quotes("CN", cn_stocks)
    for symbol, quote in cn_quotes.items():
        print(f"{quote.name:20} ({symbol:6}): ¥{quote.price:8.2f} {quote.change_pct:+7.2f}%")
    
    # 获取历史数据
    print("\\n📊 历史数据示例 (腾讯1个月)")
    print("-" * 70)
    history = client.get_price_history("HK", "0700", period="1mo")
    if history:
        print(f"共获取 {len(history)} 条记录")
        print("\\n最近5条记录:")
        for record in history[-5:]:
            print(f"  {record['date']}: 开{record['open']:.2f} 高{record['high']:.2f} "
                  f"低{record['low']:.2f} 收{record['close']:.2f} 量{record['volume']}")

if __name__ == "__main__":
    main()
''',

    f"{PROJECT_ROOT}/examples/example_technical_analysis.py": '''"""
技术分析示例 - 计算各种技术指标
"""

from scripts.unified_client import UnifiedMarketClient
from scripts.technical_indicators import (
    calculate_sma, calculate_rsi, calculate_macd, calculate_bollinger_bands
)

def main():
    client = UnifiedMarketClient()
    
    print("=" * 70)
    print("技术分析示例 - 腾讯(0700)")
    print("=" * 70)
    
    history = client.get_price_history("HK", "0700", period="1y")
    
    if not history:
        print("无法获取历史数据")
        return
    
    prices = [h['close'] for h in history]
    
    print("\\n1. 移动平均线 (MA)")
    print("-" * 70)
    sma_20 = calculate_sma(prices, 20)
    sma_50 = calculate_sma(prices, 50)
    print(f"SMA(20): {sma_20[-1]:.2f}")
    print(f"SMA(50): {sma_50[-1]:.2f}")
    
    print("\\n2. 相对强弱指数 (RSI)")
    print("-" * 70)
    rsi_14 = calculate_rsi(prices, 14)
    print(f"RSI(14): {rsi_14[-1]:.2f}")
    if rsi_14[-1] < 30:
        print("  → 超卖信号")
    elif rsi_14[-1] > 70:
        print("  → 超买信号")
    
    print("\\n3. MACD 指标")
    print("-" * 70)
    macd_data = calculate_macd(prices)
    print(f"MACD: {macd_data['macd'][-1]:.4f}")
    print(f"Signal: {macd_data['signal'][-1]:.4f}")
    
    print("\\n4. 布林带 (BB)")
    print("-" * 70)
    bb = calculate_bollinger_bands(prices, 20)
    print(f"上轨: {bb['upper'][-1]:.2f}")
    print(f"中轨: {bb['middle'][-1]:.2f}")
    print(f"下轨: {bb['lower'][-1]:.2f}")
    print(f"当前价: {prices[-1]:.2f}")

if __name__ == "__main__":
    main()
''',

    f"{PROJECT_ROOT}/examples/example_trading_signals.py": '''"""
交易信号示例 - 生成自动交易信号
"""

from scripts.unified_client import UnifiedMarketClient
from scripts.trading_signals import TradingSignalGenerator

def main():
    client = UnifiedMarketClient()
    generator = TradingSignalGenerator()
    
    print("=" * 70)
    print("交易信号生成示例")
    print("=" * 70)
    
    symbols = [
        ("US", "AAPL"),
        ("HK", "0700"),
        ("TW", "2330"),
        ("CN", "000001")
    ]
    
    for market, symbol in symbols:
        print(f"\\n📊 {symbol} ({market})")
        print("-" * 70)
        
        history = client.get_price_history(market, symbol, period="3mo")
        if not history:
            print("无法获取数据")
            continue
        
        prices = [h['close'] for h in history]
        
        signals = generator.generate_signals(prices)
        
        for strategy, signal_data in signals.items():
            print(f"\\n{strategy.upper()}")
            print(f"  信号: {signal_data['signal']}")
            print(f"  置信度: {signal_data['confidence']:.0%}")
            print(f"  原因: {signal_data['reason']}")

if __name__ == "__main__":
    main()
''',

    f"{PROJECT_ROOT}/examples/example_portfolio.py": '''"""
投资组合示例 - 跨市场投资组合管理
"""

from scripts.portfolio_analyzer import PortfolioAnalyzer

def main():
    portfolio = PortfolioAnalyzer()
    
    print("=" * 70)
    print("跨市场投资组合示例")
    print("=" * 70)
    
    print("\\n添加持仓...")
    portfolio.add_holding("AAPL", 10, 150.00, "US")
    portfolio.add_holding("0700", 100, 45.00, "HK")
    portfolio.add_holding("2330", 50, 300.00, "TW")
    portfolio.add_holding("000001", 1000, 15.00, "CN")
    
    print("\\n获取投资组合报告...")
    report = portfolio.get_summary_report()
    
    print("\\n" + "=" * 70)
    print("投资组合总结")
    print("=" * 70)
    print(f"总成本:      ¥{report['total_cost']:,.2f}")
    print(f"当前价值:    ¥{report['total_value']:,.2f}")
    print(f"总损益:      ¥{report['total_gain_loss']:+,.2f}")
    print(f"总收益率:    {report['total_return_pct']:+.2f}%")
    
    print("\\n" + "=" * 70)
    print("各市场配置")
    print("=" * 70)
    allocation = portfolio.get_market_allocation()
    for market, pct in allocation.items():
        print(f"{market}: {pct:.1f}%")
    
    print("\\n" + "=" * 70)
    print("持仓详情")
    print("=" * 70)
    print(f"{'代码':<10} {'市场':<5} {'数量':<8} {'成本':<8} {'当前':<8} {'损益':>10} {'收益率':>8}")
    print("-" * 70)
    
    for holding in report['holdings']:
        print(f"{holding['symbol']:<10} {holding['market']:<5} "
              f"{holding['quantity']:<8.0f} {holding['cost']:<8,.0f} "
              f"{holding['current_value']:<8,.0f} {holding['gain_loss']:>10,.0f} "
              f"{holding['gain_loss_pct']:>7.1f}%")

if __name__ == "__main__":
    main()
''',
}

def create_directories():
    """创建目录"""
    for directory in DIRECTORIES:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ 创建目录: {directory}")

def create_files():
    """创建文件"""
    for filepath, content in FILES.items():
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ 创建文件: {filepath}")

def main():
    print("=" * 70)
    print("🚀 生成四市场金融数据 Skills 项目")
    print("=" * 70)
    
    try:
        create_directories()
        create_files()
        
        print("\n" + "=" * 70)
        print("✨ 项目生成完成！")
        print("=" * 70)
        print(f"\n📁 项目位置: {PROJECT_ROOT}")
        print("\n📦 下一步:")
        print("1. 安装依赖: pip install -r requirements.txt")
        print("2. 运行示例: python examples/example_basic_queries.py")
        print("3. 查看其他示例文件")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
