"""
初始化行业配置数据
添加常见行业的默认PB阈值和风险参数
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import init_db, session_scope
from src.services.industry_service import IndustryService


def init_industry_configs():
    """初始化行业配置"""
    print("开始初始化行业配置...")

    init_db()

    with session_scope() as session:
        industry_service = IndustryService(session)

        # 行业配置列表
        # 格式：(行业名, 显示名, 描述, 买入PB, 加仓PB, 卖出PB, PB最小, PB最大, 典型ROE, 是否周期, 推荐最大仓位, 风险等级)
        industries = [
            # 消费类
            (
                "白酒", "白酒", "高端白酒行业",
                5.0, 4.0, 8.0, 3.0, 12.0, 25.0, False, 10.0, "low"
            ),
            (
                "食品饮料", "食品饮料", "食品饮料制造业",
                3.0, 2.5, 5.0, 2.0, 8.0, 15.0, False, 10.0, "low"
            ),
            (
                "家电", "家电", "家用电器制造业",
                2.0, 1.5, 3.5, 1.5, 5.0, 20.0, True, 8.0, "medium"
            ),

            # 科技类
            (
                "软件服务", "软件服务", "软件和信息技术服务业",
                4.0, 3.0, 7.0, 2.0, 10.0, 15.0, False, 10.0, "medium"
            ),
            (
                "半导体", "半导体", "半导体及电子元件",
                3.0, 2.0, 6.0, 1.5, 10.0, 10.0, True, 8.0, "high"
            ),
            (
                "通信设备", "通信设备", "通信设备制造业",
                2.5, 2.0, 4.5, 1.5, 7.0, 12.0, True, 8.0, "medium"
            ),

            # 医药类
            (
                "医药生物", "医药生物", "医药制造业",
                4.0, 3.0, 7.0, 2.5, 10.0, 18.0, False, 10.0, "medium"
            ),
            (
                "医疗器械", "医疗器械", "医疗器械及服务",
                3.5, 2.5, 6.0, 2.0, 9.0, 15.0, False, 10.0, "medium"
            ),

            # 金融类
            (
                "银行", "银行", "银行业",
                0.7, 0.6, 1.2, 0.5, 1.5, 12.0, True, 15.0, "low"
            ),
            (
                "保险", "保险", "保险业",
                1.0, 0.8, 1.8, 0.7, 2.5, 15.0, True, 12.0, "medium"
            ),
            (
                "券商", "券商", "证券业",
                1.5, 1.2, 2.5, 1.0, 4.0, 10.0, True, 10.0, "high"
            ),

            # 地产建筑
            (
                "房地产", "房地产", "房地产开发经营",
                1.0, 0.8, 1.8, 0.6, 3.0, 10.0, True, 5.0, "high"
            ),
            (
                "建筑装饰", "建筑装饰", "建筑装饰业",
                1.2, 1.0, 2.0, 0.8, 3.0, 12.0, True, 8.0, "medium"
            ),

            # 周期类
            (
                "化工", "化工", "化学原料及化学制品制造业",
                1.5, 1.2, 2.5, 1.0, 4.0, 10.0, True, 8.0, "high"
            ),
            (
                "钢铁", "钢铁", "黑色金属冶炼及压延加工业",
                0.8, 0.6, 1.5, 0.5, 2.5, 8.0, True, 5.0, "high"
            ),
            (
                "有色金属", "有色金属", "有色金属冶炼及压延加工业",
                1.2, 1.0, 2.0, 0.8, 3.5, 10.0, True, 8.0, "high"
            ),
            (
                "煤炭", "煤炭", "煤炭开采和洗选业",
                1.0, 0.8, 1.8, 0.6, 3.0, 15.0, True, 8.0, "high"
            ),

            # 制造类
            (
                "汽车", "汽车", "汽车制造业",
                1.5, 1.2, 2.5, 1.0, 4.0, 12.0, True, 8.0, "medium"
            ),
            (
                "机械设备", "机械设备", "通用设备制造业",
                2.0, 1.5, 3.5, 1.2, 5.0, 15.0, True, 8.0, "medium"
            ),
            (
                "电力设备", "电力设备", "电气机械及器材制造业",
                2.5, 2.0, 4.0, 1.5, 6.0, 18.0, False, 10.0, "medium"
            ),

            # 公用事业
            (
                "电力", "电力", "电力、热力生产和供应业",
                1.2, 1.0, 2.0, 0.8, 2.5, 8.0, False, 10.0, "low"
            ),
            (
                "环保", "环保", "生态保护和环境治理业",
                2.0, 1.5, 3.5, 1.2, 5.0, 12.0, False, 8.0, "medium"
            ),

            # 新能源
            (
                "光伏", "光伏", "太阳能发电设备制造",
                3.0, 2.5, 5.0, 2.0, 8.0, 15.0, True, 8.0, "high"
            ),
            (
                "新能源车", "新能源车", "新能源汽车及零部件",
                3.5, 2.5, 6.0, 2.0, 10.0, 12.0, False, 10.0, "high"
            ),

            # 互联网
            (
                "互联网", "互联网", "互联网和相关服务",
                3.0, 2.5, 5.5, 2.0, 8.0, 20.0, False, 10.0, "medium"
            ),
            (
                "传媒", "传媒", "广播、电视、电影和影视录音制作业",
                2.5, 2.0, 4.5, 1.5, 6.0, 15.0, False, 8.0, "medium"
            ),

            # 其他
            (
                "商贸零售", "商贸零售", "零售业",
                2.0, 1.5, 3.5, 1.2, 5.0, 15.0, False, 8.0, "medium"
            ),
            (
                "交通运输", "交通运输", "交通运输、仓储和邮政业",
                1.5, 1.2, 2.5, 1.0, 4.0, 10.0, True, 8.0, "medium"
            ),
        ]

        for industry_data in industries:
            (
                name, display, desc, buy_pb, add_pb, sell_pb,
                pb_min, pb_max, roe, cyclical, max_pos, risk
            ) = industry_data

            industry_service.create_or_update_industry(
                industry_name=name,
                display_name=display,
                description=desc,
                default_buy_pb=buy_pb,
                default_add_pb=add_pb,
                default_sell_pb=sell_pb,
                typical_pb_range_min=pb_min,
                typical_pb_range_max=pb_max,
                typical_roe=roe,
                cyclical=cyclical,
                recommended_max_position=max_pos,
                risk_level=risk
            )
            print(f"  [OK] {name}")

    print(f"\n行业配置初始化完成！共 {len(industries)} 个行业")


if __name__ == "__main__":
    init_industry_configs()
