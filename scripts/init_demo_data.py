"""Initialize demo data for testing."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta
import random
from src.database import init_db, get_session
from src.database.models import Asset, Threshold, Valuation, Market

def create_demo_data():
    """Create demo stocks and valuation data."""
    init_db()
    session = get_session()

    # Demo stocks
    demo_stocks = [
        {
            "code": "600519.SH",
            "name": "贵州茅台",
            "market": Market.A_SHARE,
            "industry": "白酒",
            "competence_score": 5,
            "notes": "中国白酒龙头，品牌护城河极深，提价能力强",
            "buy_pb": 8.0,
            "add_pb": 6.0,
            "sell_pb": 15.0
        },
        {
            "code": "000858.SZ",
            "name": "五粮液",
            "market": Market.A_SHARE,
            "industry": "白酒",
            "competence_score": 4,
            "notes": "浓香型白酒龙头，品牌力强",
            "buy_pb": 5.0,
            "add_pb": 4.0,
            "sell_pb": 10.0
        },
        {
            "code": "601318.SH",
            "name": "中国平安",
            "market": Market.A_SHARE,
            "industry": "保险",
            "competence_score": 4,
            "notes": "综合金融龙头，寿险+财险+银行+科技",
            "buy_pb": 1.0,
            "add_pb": 0.8,
            "sell_pb": 2.0
        },
        {
            "code": "0700.HK",
            "name": "腾讯控股",
            "market": Market.HK,
            "industry": "互联网",
            "competence_score": 5,
            "notes": "社交+游戏+投资，生态护城河",
            "buy_pb": 3.0,
            "add_pb": 2.5,
            "sell_pb": 6.0
        },
        {
            "code": "000002.SZ",
            "name": "万科A",
            "market": Market.A_SHARE,
            "industry": "房地产",
            "competence_score": 3,
            "notes": "地产龙头，但行业承压",
            "buy_pb": 0.6,
            "add_pb": 0.5,
            "sell_pb": 1.2
        }
    ]

    for stock_data in demo_stocks:
        # Check if exists
        existing = session.query(Asset).filter(Asset.code == stock_data["code"]).first()
        if existing:
            print(f"Stock {stock_data['code']} already exists, skipping...")
            continue

        # Create asset
        asset = Asset(
            code=stock_data["code"],
            name=stock_data["name"],
            market=stock_data["market"],
            industry=stock_data["industry"],
            competence_score=stock_data["competence_score"],
            notes=stock_data["notes"]
        )
        session.add(asset)
        session.flush()

        # Create threshold
        threshold = Threshold(
            asset_id=asset.id,
            buy_pb=stock_data["buy_pb"],
            add_pb=stock_data.get("add_pb"),
            sell_pb=stock_data.get("sell_pb")
        )
        session.add(threshold)

        # Generate fake PB history (last 2 years)
        base_pb = stock_data["buy_pb"] * 1.2  # Start slightly above buy threshold
        today = date.today()

        for i in range(365 * 2):  # 2 years of data
            val_date = today - timedelta(days=i)
            if val_date.weekday() >= 5:  # Skip weekends
                continue

            # Random walk with mean reversion
            noise = random.gauss(0, 0.02)
            mean_reversion = (base_pb - base_pb * 1.1) * 0.01
            pb_change = noise + mean_reversion

            base_pb = max(base_pb * (1 + pb_change), stock_data["buy_pb"] * 0.5)
            base_pb = min(base_pb, stock_data["sell_pb"] * 1.2 if stock_data.get("sell_pb") else base_pb)

            valuation = Valuation(
                asset_id=asset.id,
                date=val_date,
                pb=round(base_pb, 2),
                price=round(base_pb * 10 + random.uniform(-5, 5), 2),  # Fake price
                data_source="demo"
            )
            session.add(valuation)

        print(f"Created demo data for {stock_data['name']} ({stock_data['code']})")

    session.commit()
    session.close()
    print("\nDemo data initialization complete!")

if __name__ == "__main__":
    create_demo_data()
