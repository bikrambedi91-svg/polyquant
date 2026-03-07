"""Generate PolyQuant Architecture PowerPoint presentation."""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ── Colors ──
DARK_BG = RGBColor(0x1A, 0x1A, 0x2E)
ACCENT_BLUE = RGBColor(0x00, 0x96, 0xFF)
ACCENT_GREEN = RGBColor(0x00, 0xD4, 0xAA)
ACCENT_ORANGE = RGBColor(0xFF, 0x8C, 0x00)
ACCENT_RED = RGBColor(0xFF, 0x45, 0x45)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_GRAY = RGBColor(0xCC, 0xCC, 0xCC)
MID_GRAY = RGBColor(0x88, 0x88, 0x99)
DARK_CARD = RGBColor(0x25, 0x25, 0x40)
HEADER_BG = RGBColor(0x0D, 0x0D, 0x1A)


def set_slide_bg(slide, color):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_text_box(slide, left, top, width, height, text, font_size=14,
                 color=WHITE, bold=False, align=PP_ALIGN.LEFT, font_name="Segoe UI"):
    txBox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.color.rgb = color
    p.font.bold = bold
    p.font.name = font_name
    p.alignment = align
    return txBox


def add_bullet_list(slide, left, top, width, height, items, font_size=13,
                    color=LIGHT_GRAY, bullet_color=ACCENT_BLUE):
    txBox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = f"▸ {item}"
        p.font.size = Pt(font_size)
        p.font.color.rgb = color
        p.font.name = "Segoe UI"
        p.space_after = Pt(4)
    return txBox


def add_card(slide, left, top, width, height, title, body_items,
             accent=ACCENT_BLUE, font_size=12):
    # Card background
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top),
        Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = DARK_CARD
    shape.line.fill.background()

    # Accent line
    line = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(left), Inches(top),
        Inches(width), Inches(0.04)
    )
    line.fill.solid()
    line.fill.fore_color.rgb = accent
    line.line.fill.background()

    # Title
    add_text_box(slide, left + 0.15, top + 0.08, width - 0.3, 0.3,
                 title, font_size=14, color=accent, bold=True)

    # Body
    add_bullet_list(slide, left + 0.15, top + 0.42, width - 0.3, height - 0.5,
                    body_items, font_size=font_size, color=LIGHT_GRAY)


def add_stat_box(slide, left, top, width, number, label, color=ACCENT_BLUE):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top),
        Inches(width), Inches(0.9)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = DARK_CARD
    shape.line.fill.background()

    add_text_box(slide, left, top + 0.05, width, 0.45,
                 str(number), font_size=28, color=color, bold=True, align=PP_ALIGN.CENTER)
    add_text_box(slide, left, top + 0.5, width, 0.35,
                 label, font_size=10, color=MID_GRAY, align=PP_ALIGN.CENTER)


def create_presentation():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # ════════════════════════════════════════════
    # SLIDE 1: Title
    # ════════════════════════════════════════════
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank
    set_slide_bg(slide, DARK_BG)

    add_text_box(slide, 1.5, 1.5, 10, 1.2,
                 "PolyQuant", font_size=54, color=ACCENT_BLUE, bold=True,
                 align=PP_ALIGN.CENTER)
    add_text_box(slide, 1.5, 2.7, 10, 0.7,
                 "Self-Learning Crypto Trading Bot", font_size=28, color=WHITE,
                 align=PP_ALIGN.CENTER)
    add_text_box(slide, 1.5, 3.5, 10, 0.5,
                 "Architecture Overview — March 2026", font_size=16, color=MID_GRAY,
                 align=PP_ALIGN.CENTER)

    # Stats row
    stats = [("7", "Quant Models"), ("386", "Tests Passing"),
             ("~8,500", "Lines of Code"), ("3", "Market Tiers"),
             ("$20", "Fixed Position")]
    for i, (num, label) in enumerate(stats):
        add_stat_box(slide, 1.8 + i * 2.0, 4.8, 1.8, num, label)

    add_text_box(slide, 1.5, 6.2, 10, 0.4,
                 "7 models  ·  Polymarket binary options  ·  Adaptive learning  ·  Paper → Live graduation",
                 font_size=13, color=MID_GRAY, align=PP_ALIGN.CENTER)

    # ════════════════════════════════════════════
    # SLIDE 2: System Architecture
    # ════════════════════════════════════════════
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, DARK_BG)

    add_text_box(slide, 0.5, 0.3, 12, 0.6,
                 "System Architecture", font_size=32, color=WHITE, bold=True)
    add_text_box(slide, 0.5, 0.85, 12, 0.4,
                 "Modular pipeline with self-learning feedback loop",
                 font_size=14, color=MID_GRAY)

    # Architecture boxes — left column (Data Sources)
    add_card(slide, 0.5, 1.5, 2.8, 2.0, "DATA SOURCES", [
        "Binance (OHLCV, Funding)",
        "Fear & Greed Index",
        "CryptoQuant (on-chain)",
        "Deribit (options IV)",
    ], accent=ACCENT_ORANGE)

    # Middle-left column (Models)
    add_card(slide, 3.6, 1.5, 2.8, 2.0, "7 QUANT MODELS", [
        "MomentumRegime (ADX/DI)",
        "FundingBasis (contrarian)",
        "TechConfluence (RSI/MACD)",
        "CLOBSignal (book imbalance)",
        "+ VolSurf, Sentiment, ChainFlow",
    ], accent=ACCENT_BLUE)

    # Middle column (Ensemble → Market)
    add_card(slide, 6.7, 1.5, 2.8, 2.0, "ENSEMBLE + MARKET", [
        "Bayesian weighted avg",
        "Polymarket scanner (Gamma)",
        "CLOB order book analysis",
        "Fee-aware edge calculation",
    ], accent=ACCENT_GREEN)

    # Right column (Execution)
    add_card(slide, 9.8, 1.5, 2.8, 2.0, "EXECUTION", [
        "15m: Maker-only (GTC)",
        "1h/4h: FOK taker (0% fee)",
        "4% SL / 7% TP (flat)",
        "2s fast monitor",
    ], accent=ACCENT_RED)

    # Bottom row — Learning + DB + Dashboard
    add_card(slide, 0.5, 4.0, 3.8, 2.0, "LEARNING ENGINE", [
        "Brier score evaluation",
        "Optuna param optimization",
        "Adaptive SL/TP from MAE/MFE",
        "Model evolution pipeline",
        "WARNING → CRITICAL → RETIRED",
    ], accent=ACCENT_ORANGE)

    add_card(slide, 4.6, 4.0, 3.8, 2.0, "DATABASE + RISK", [
        "SQLite WAL (dev) / PostgreSQL",
        "Trade, Signal, LearningEvent tables",
        "Max 3 open positions",
        "$100/day loss halt",
        "40% net directional limit",
    ], accent=ACCENT_BLUE)

    add_card(slide, 8.7, 4.0, 3.8, 2.0, "DASHBOARD", [
        "Streamlit 7-tab UI",
        "Overview, Positions, History",
        "Analytics, Risk Monitor",
        "Signal Explorer, Learning Engine",
    ], accent=ACCENT_GREEN)

    # Flow arrows (text-based)
    add_text_box(slide, 3.15, 2.2, 0.5, 0.3, "→", font_size=24, color=ACCENT_BLUE,
                 align=PP_ALIGN.CENTER)
    add_text_box(slide, 6.25, 2.2, 0.5, 0.3, "→", font_size=24, color=ACCENT_GREEN,
                 align=PP_ALIGN.CENTER)
    add_text_box(slide, 9.35, 2.2, 0.5, 0.3, "→", font_size=24, color=ACCENT_RED,
                 align=PP_ALIGN.CENTER)

    # ════════════════════════════════════════════
    # SLIDE 3: The 7 Models
    # ════════════════════════════════════════════
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, DARK_BG)

    add_text_box(slide, 0.5, 0.3, 12, 0.6,
                 "The 7 Quant Models", font_size=32, color=WHITE, bold=True)
    add_text_box(slide, 0.5, 0.85, 12, 0.4,
                 "Each model outputs (prob_up, confidence) — ensemble combines them with timeframe-specific weights",
                 font_size=14, color=MID_GRAY)

    models_data = [
        ("MomentumRegime", "ADX + DI trend classification. Fast-reacting across all TFs.", "20%/18%/16%", ACCENT_BLUE),
        ("FundingBasis", "Perp funding rate contrarian signal. Better on longer TFs.", "10%/18%/22%", ACCENT_GREEN),
        ("ChainFlow", "Exchange net flows. Slow data — disabled on 5m/15m.", "0%/12%/18%", ACCENT_ORANGE),
        ("VolSurface", "IV skew + realized vol from ATR/Deribit.", "8%/14%/15%", ACCENT_BLUE),
        ("Sentiment", "Fear & Greed Index. Updates daily — disabled on 5m/15m.", "0%/8%/13%", ACCENT_GREEN),
        ("TechConfluence", "RSI/MACD/BB/VWAP/Volume confluence scoring.", "32%/20%/16%", ACCENT_ORANGE),
        ("CLOBSignal", "Polymarket book imbalance + large trades. Crucial on 15m.", "30%/10%/0%", ACCENT_RED),
    ]

    for i, (name, desc, weights, color) in enumerate(models_data):
        y = 1.4 + i * 0.78
        # Model name
        add_text_box(slide, 0.7, y, 2.5, 0.35, name, font_size=16, color=color, bold=True)
        # Description
        add_text_box(slide, 3.3, y, 6.5, 0.35, desc, font_size=13, color=LIGHT_GRAY)
        # Weights
        add_text_box(slide, 10.0, y, 2.5, 0.35, f"15m / 1h / 4h: {weights}",
                     font_size=11, color=MID_GRAY)
        # Separator line
        if i < 6:
            line = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(0.7), Inches(y + 0.55),
                Inches(11.5), Inches(0.01)
            )
            line.fill.solid()
            line.fill.fore_color.rgb = RGBColor(0x33, 0x33, 0x50)
            line.line.fill.background()

    # ════════════════════════════════════════════
    # SLIDE 4: Trading Pipeline
    # ════════════════════════════════════════════
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, DARK_BG)

    add_text_box(slide, 0.5, 0.3, 12, 0.6,
                 "13-Step Trading Pipeline", font_size=32, color=WHITE, bold=True)
    add_text_box(slide, 0.5, 0.85, 12, 0.4,
                 "Executes every 30 seconds per timeframe — 2s fast monitor for active positions",
                 font_size=14, color=MID_GRAY)

    steps = [
        ("1", "Regime Detection", "RISK_ON / OFF / HIGH_VOL / TRENDING / CHOPPY"),
        ("2", "Data Collection", "OHLCV from Binance via ccxt (async)"),
        ("3", "Signal Generation", "7 models → (prob_up, confidence) each"),
        ("4", "Ensemble Aggregation", "Bayesian weighted average with disagreement check"),
        ("5", "Market Discovery", "Gamma API → filter by volume, TTR, timeframe"),
        ("6", "Order Book Analysis", "CLOB API → slippage, depth, best bid/ask"),
        ("7", "Edge Calculation", "edge = |our_prob - effective_implied| - fees - slippage"),
        ("8", "Position Sizing", "Fixed $20 per trade (replaced Kelly)"),
        ("9", "Risk Check", "Max 3 open, $100 daily halt, directional limits"),
        ("10", "Trade Execution", "15m maker / 1h+4h FOK → stored in DB"),
        ("11", "Position Monitoring", "TP/SL check every 2s (fast monitor)"),
        ("12", "Feedback Recording", "MAE, MFE, PnL → FeedbackStore"),
        ("13", "Learning Cycle", "Brier scores, Optuna, SL/TP optimization"),
    ]

    # Left column (steps 1-7)
    for i, (num, title, desc) in enumerate(steps[:7]):
        y = 1.4 + i * 0.75
        add_text_box(slide, 0.5, y, 0.5, 0.3, num, font_size=18, color=ACCENT_BLUE,
                     bold=True, align=PP_ALIGN.CENTER)
        add_text_box(slide, 1.1, y, 2.0, 0.3, title, font_size=14, color=WHITE, bold=True)
        add_text_box(slide, 1.1, y + 0.28, 5.0, 0.3, desc, font_size=11, color=MID_GRAY)

    # Right column (steps 8-13)
    for i, (num, title, desc) in enumerate(steps[7:]):
        y = 1.4 + i * 0.75
        add_text_box(slide, 6.8, y, 0.5, 0.3, num, font_size=18, color=ACCENT_GREEN,
                     bold=True, align=PP_ALIGN.CENTER)
        add_text_box(slide, 7.4, y, 2.5, 0.3, title, font_size=14, color=WHITE, bold=True)
        add_text_box(slide, 7.4, y + 0.28, 5.0, 0.3, desc, font_size=11, color=MID_GRAY)

    # ════════════════════════════════════════════
    # SLIDE 5: Market Tiers & Execution
    # ════════════════════════════════════════════
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, DARK_BG)

    add_text_box(slide, 0.5, 0.3, 12, 0.6,
                 "Market Tiers & Execution Strategy", font_size=32, color=WHITE, bold=True)

    # Three tier cards
    add_card(slide, 0.5, 1.2, 3.8, 3.2, "15-MINUTE MARKETS", [
        "3% max taker fee (at 50% prob)",
        "Strategy: MAKER-ONLY orders",
        "Buy one tick below best ask",
        "GTC limit order → 0% fee",
        "Earns USDC rebates",
        "Be very selective (11%+ edge)",
        "Fast monitor: 2s intervals",
    ], accent=ACCENT_ORANGE, font_size=13)

    add_card(slide, 4.7, 1.2, 3.8, 3.2, "1-HOUR MARKETS", [
        "0% taker fee (free!)",
        "Strategy: FOK market orders",
        "Fill-or-Kill instant entry",
        "Walk the book for fill price",
        "Edge threshold: 8% (BUY_NO)",
        "Re-entry system (max 3/market)",
        "Fast monitor: 2s intervals",
    ], accent=ACCENT_BLUE, font_size=13)

    add_card(slide, 8.9, 1.2, 3.8, 3.2, "4-HOUR MARKETS", [
        "0% taker fee (free!)",
        "Strategy: FOK market orders",
        "Same as 1h execution",
        "Higher volume threshold",
        "Longer resolution window",
        "ChainFlow + Sentiment active",
        "Fast monitor: 2s intervals",
    ], accent=ACCENT_GREEN, font_size=13)

    # TP/SL section
    add_card(slide, 0.5, 4.8, 6.0, 2.2, "TP/SL SYSTEM (FLAT)", [
        "Stop-Loss: 4% flat (all markets, all timeframes)",
        "Take-Profit: 7% flat (regardless of confidence/regime)",
        "BUY_YES: TP = entry × 1.07,  SL = entry × 0.96",
        "BUY_NO:  TP = entry - 0.07×(1-entry),  SL = entry + 0.04×(1-entry)",
        "Max hold: 600 seconds (10 min) → forced exit",
    ], accent=ACCENT_RED, font_size=13)

    add_card(slide, 6.8, 4.8, 6.0, 2.2, "RISK MANAGEMENT", [
        "Fixed position size: $20 per trade",
        "Max 3 open positions simultaneously",
        "Daily loss halt: $100 USD",
        "Max per asset: 25% of bankroll",
        "Max total exposure: 60% of bankroll",
        "Max net directional: 40% of bankroll",
    ], accent=ACCENT_BLUE, font_size=13)

    # ════════════════════════════════════════════
    # SLIDE 6: Learning Engine
    # ════════════════════════════════════════════
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, DARK_BG)

    add_text_box(slide, 0.5, 0.3, 12, 0.6,
                 "Self-Learning Engine", font_size=32, color=WHITE, bold=True)
    add_text_box(slide, 0.5, 0.85, 12, 0.4,
                 "The bot gets smarter with every trade — recalibrates every 50 trades or weekly",
                 font_size=14, color=MID_GRAY)

    # Model lifecycle
    add_card(slide, 0.5, 1.4, 4.0, 2.5, "MODEL LIFECYCLE", [
        "ACTIVE → runs in ensemble normally",
        "WARNING (Brier > 0.28) → weight -30%",
        "CRITICAL (Brier > 0.35) → near-zero weight",
        "RETIRED (2× CRITICAL) → graveyard",
        "Minimum 4 active models always",
        "Max 1 retired per cycle",
    ], accent=ACCENT_ORANGE)

    add_card(slide, 4.8, 1.4, 4.0, 2.5, "PARAMETER OPTIMIZATION", [
        "Optuna walk-forward search",
        "60% train / 20% validate / 20% holdout",
        "Minimum 80 trades required",
        "Overfit check: val > train + 0.05",
        "Max param change: 50% from default",
        "Probation: 30 shadow trades first",
    ], accent=ACCENT_BLUE)

    add_card(slide, 9.1, 1.4, 3.7, 2.5, "SL/TP LEARNING", [
        "Simulate SL: 2%-15% range",
        "Simulate TP: 2%-40% range",
        "Uses MAE/MFE (% of cost basis)",
        "Per (asset, TF, regime) bucket",
        "Min 30 trades per bucket",
        "Max 3% change per cycle",
    ], accent=ACCENT_GREEN)

    # Safety rails
    add_card(slide, 0.5, 4.2, 6.0, 2.8, "SAFETY RAILS (NEVER VIOLATE)", [
        "Max 1 model mutated per recalibration cycle",
        "Max 1 model retired per cycle",
        "Minimum 4 active models at all times",
        "Max parameter change: 50% from default per mutation",
        "Max SL/TP change: 3% per cycle",
        "Max ensemble weight change: 15% per cycle",
        "Optuna needs minimum 80 trades (not 50)",
        "All mutated params must pass constraint validation",
        "Learning engine dormant for first 50 trades (cold start)",
    ], accent=ACCENT_RED, font_size=12)

    add_card(slide, 6.8, 4.2, 6.0, 2.8, "GRADUATION: PAPER → LIVE", [
        "≥ 100 paper trades",
        "Win rate > 54%",
        "Total P&L > 0",
        "Sharpe ratio > 0.8",
        "Calibration error < 0.15",
        "No single day drawdown > 6% in last 30 days",
        "≥ 14 calendar days of paper trading",
        "≥ 2 recalibration cycles completed",
        "First 48h live at half-size (50%)",
    ], accent=ACCENT_GREEN, font_size=12)

    # ════════════════════════════════════════════
    # SLIDE 7: Tech Stack & Deployment
    # ════════════════════════════════════════════
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, DARK_BG)

    add_text_box(slide, 0.5, 0.3, 12, 0.6,
                 "Tech Stack & Project Structure", font_size=32, color=WHITE, bold=True)

    add_card(slide, 0.5, 1.2, 3.8, 2.8, "TECH STACK", [
        "Python 3.14 (async/await)",
        "SQLAlchemy + SQLite WAL",
        "ccxt (Binance/Coinbase)",
        "py_clob_client (Polymarket)",
        "ta library (pure Python)",
        "Optuna (hyperparameter search)",
        "structlog (JSON logging)",
        "Streamlit (dashboard)",
    ], accent=ACCENT_BLUE)

    add_card(slide, 4.7, 1.2, 3.8, 2.8, "PROJECT STRUCTURE", [
        "config/ — Settings, constants",
        "data/ — Price, funding, sentiment feeds",
        "database/ — ORM, trade CRUD",
        "models/ — 7 models + ensemble",
        "market/ — Scanner, orderbook, pricing",
        "execution/ — Paper/live engine, TP/SL",
        "learning/ — Feedback, evolution, Optuna",
        "orchestrator/ — Pipeline, loop, graduation",
    ], accent=ACCENT_GREEN)

    add_card(slide, 8.9, 1.2, 3.8, 2.8, "EXTERNAL APIs", [
        "Polymarket Gamma (discovery)",
        "Polymarket CLOB (order book)",
        "Binance (OHLCV + funding)",
        "Coinbase (fallback OHLCV)",
        "Fear & Greed API (sentiment)",
        "Deribit (options IV, optional)",
        "CryptoQuant (on-chain, optional)",
    ], accent=ACCENT_ORANGE)

    # Bottom — Key numbers
    add_card(slide, 0.5, 4.3, 12.3, 2.7, "KEY DESIGN DECISIONS", [
        "Protocol-based DI: SLTPProvider interface → DefaultSLTPProvider / LearnedSLTPProvider swappable",
        "Dual-loop architecture: 30s main cycle (signals, trades) + 2s fast monitor (TP/SL exits)",
        "Non-blocking CLOB: asyncio.to_thread() wraps synchronous py_clob_client calls",
        "Fee-aware market tiers: 15m maker-only avoids 3% fee, 1h/4h are free taker",
        "BUY_YES edge premium: +4% edge requirement because bullish predictions are systematically overconfident",
        "Flat TP/SL (4%/7%): Wins outpace losses even with SL gapping on binary options",
        "Re-entry guards: After TP → allow re-entry; after SL → block; max 3 entries per market",
        "Fill slippage rejection: 15m has 3¢ max deviation, 1h/4h have 5¢ — prevents thin-book entries",
    ], accent=ACCENT_BLUE, font_size=12)

    # ════════════════════════════════════════════
    # Save
    # ════════════════════════════════════════════
    output_path = r"C:\polyquant\docs\PolyQuant_Architecture.pptx"
    prs.save(output_path)
    print(f"Presentation saved to: {output_path}")
    print(f"Slides: {len(prs.slides)}")


if __name__ == "__main__":
    create_presentation()
