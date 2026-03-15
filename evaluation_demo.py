#!/usr/bin/env python
"""
UniLLM Platform 评测演示脚本
演示如何使用平台进行模型评测
"""

import sys
import time
import json
from pathlib import Path

try:
    import httpx
except ImportError:
    print("请先安装依赖: pip install httpx")
    sys.exit(1)

BASE_URL = "http://localhost:8000"


class EvaluationDemo:
    def __init__(self):
        self.client = httpx.Client(timeout=60.0)
        self.dataset_id = None
        self.model_id = None
        self.eval_id = None
        print("=" * 70)
        print("UniLLM Platform 评测演示")
        print("=" * 70)
    
    def check_server(self):
        """检查服务器是否启动"""
        print("\n[步骤 1] 检查服务器连接...")
        try:
            response = self.client.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                print("✓ 服务器连接成功！")
                print(f"  状态: {response.json()['status']}")
                print(f"  版本: {response.json()['version']}")
                return True
        except:
            pass
        
        print("✗ 服务器未启动或连接失败")
        print("\n请先启动服务器:")
        print("  cd unillm-platform")
        print("  python -m app.main")
        return False
    
    def demo_mock_evaluation(self):
        """模拟评测演示（无需启动服务器）"""
        print("\n" + "=" * 70)
        print("模式: 模拟评测演示")
        print("=" * 70)
        
        print("\n[步骤 1] 准备测试数据")
        test_data = [
            {"instruction": "什么是机器学习？", "output": "机器学习是人工智能的一个分支..."},
            {"instruction": "解释深度学习的概念", "output": "深度学习是机器学习的一个子领域..."},
            {"instruction": "什么是自然语言处理？", "output": "自然语言处理是人工智能的交叉领域..."},
        ]
        print(f"✓ 准备了 {len(test_data)} 条测试数据")
        
        print("\n[步骤 2] 创建数据集")
        print("  • 数据集名称: 评测测试数据集")
        print("  • 数据类型: 问答数据")
        
        print("\n[步骤 3] 注册模型")
        print("  • 模型名称: demo-model")
        print("  • 基座模型: Qwen/Qwen2.5-7B-Instruct")
        
        print("\n[步骤 4] 创建评测任务")
        print("  • 评测名称: 模型质量评测")
        print("  • 评测指标: Perplexity, Accuracy, Latency")
        
        print("\n[步骤 5] 运行评测...")
        time.sleep(1)
        print("  [ 10% ] 初始化评测引擎...")
        time.sleep(0.5)
        print("  [ 30% ] 计算 Perplexity...")
        time.sleep(0.5)
        print("  [ 60% ] 计算 Accuracy...")
        time.sleep(0.5)
        print("  [ 85% ] 测量 Latency...")
        time.sleep(0.5)
        print("  [100% ] 评测完成！")
        
        print("\n" + "=" * 70)
        print("评测报告")
        print("=" * 70)
        print("\n📊 通用指标")
        print("  Perplexity:    12.50    ██████░░░░  (一般)")
        print("  Accuracy:      0.72     █████░░░░░  (良好)")
        print("  F1 Score:      0.68     █████░░░░░  (良好)")
        
        print("\n⚡ 性能指标")
        print("  Avg Latency:   280ms    ██████░░░░  (良好)")
        print("  P99 Latency:   420ms    ██████░░░░  (良好)")
        print("  Throughput:    32 req/s ██████░░░░  (良好)")
        
        print("\n📈 指标解读")
        print("  • Perplexity 12.5: 模型对文本的理解能力中等")
        print("  • Accuracy 0.72: 问答任务表现良好")
        print("  • Latency 280ms: 响应速度良好，可用于生产")
        
        print("\n💡 改进建议")
        print("  1. 增加高质量训练数据，可进一步降低 Perplexity")
        print("  2. 针对特定领域微调，可提升 Accuracy")
        print("  3. 使用 vLLM 优化，可进一步降低 Latency")
        
        print("\n" + "=" * 70)
        print("模拟评测演示完成！")
        print("=" * 70)
    
    def run_real_evaluation(self):
        """真实评测流程"""
        print("\n" + "=" * 70)
        print("模式: 真实评测流程")
        print("=" * 70)
        
        print("\n[步骤 1] 导入测试数据...")
        try:
            data_path = Path("data/datasets/sample_data.jsonl")
            if data_path.exists():
                with open(data_path, "rb") as f:
                    response = self.client.post(
                        f"{BASE_URL}/api/data/import",
                        params={"name": "评测测试数据", "description": "用于评测的测试数据"},
                        files={"file": f}
                    )
                if response.status_code == 200:
                    self.dataset_id = response.json()["id"]
                    print(f"✓ 数据导入成功，数据集ID: {self.dataset_id}")
                else:
                    print(f"⚠ 数据导入返回: {response.status_code}")
            else:
                print("⚠ 测试数据文件不存在")
        except Exception as e:
            print(f"⚠ 数据导入跳过: {e}")
        
        print("\n[步骤 2] 注册模型...")
        try:
            response = self.client.post(
                f"{BASE_URL}/api/model/register",
                params={
                    "name": "evaluation-model",
                    "base_model": "Qwen/Qwen2.5-7B-Instruct",
                    "description": "用于评测演示的模型"
                }
            )
            if response.status_code == 200:
                self.model_id = response.json()["id"]
                print(f"✓ 模型注册成功，模型ID: {self.model_id}")
            else:
                print(f"⚠ 模型注册返回: {response.status_code}")
        except Exception as e:
            print(f"⚠ 模型注册跳过: {e}")
        
        print("\n[步骤 3] 创建评测任务...")
        try:
            eval_data = {
                "model_id": self.model_id or 1,
                "eval_name": "模型质量综合评测",
                "dataset_id": self.dataset_id or 1,
                "metrics": ["perplexity", "accuracy", "latency"]
            }
            response = self.client.post(
                f"{BASE_URL}/api/evaluate/create",
                json=eval_data
            )
            if response.status_code == 200:
                self.eval_id = response.json()["id"]
                print(f"✓ 评测任务创建成功，评测ID: {self.eval_id}")
            else:
                print(f"⚠ 评测任务创建返回: {response.status_code}")
        except Exception as e:
            print(f"⚠ 评测任务创建跳过: {e}")
        
        print("\n[步骤 4] 运行评测...")
        if self.eval_id:
            try:
                response = self.client.post(f"{BASE_URL}/api/evaluate/{self.eval_id}/run")
                print("✓ 评测已启动")
                print("\n提示: 实际评测需要模型加载和计算资源")
                print("      这里展示完整流程，结果将在后台计算")
            except Exception as e:
                print(f"⚠ 评测运行跳过: {e}")
        
        print("\n" + "=" * 70)
        print("真实评测流程演示完成！")
        print("=" * 70)
    
    def show_evaluation_guide(self):
        """显示评测指南"""
        print("\n" + "=" * 70)
        print("评测指标详细解读")
        print("=" * 70)
        
        print("\n📊 Perplexity (困惑度)")
        print("  含义: 衡量模型对文本的预测能力")
        print("  解读:")
        print("    < 5    → 非常优秀")
        print("    5-10   → 优秀")
        print("    10-20  → 一般")
        print("    >20    → 需改进")
        
        print("\n🎯 Accuracy (准确率)")
        print("  含义: 分类/选择任务的正确率")
        print("  解读:")
        print("    >0.95  → 非常优秀")
        print("    0.85-0.95 → 优秀")
        print("    0.75-0.85 → 良好")
        print("    <0.65  → 需改进")
        
        print("\n⚡ Latency (延迟)")
        print("  含义: 模型响应时间")
        print("  解读:")
        print("    <100ms  → 即时响应")
        print("    100-300ms → 非常流畅")
        print("    300-500ms → 流畅")
        print("    >1s     → 需优化")
        
        print("\n" + "=" * 70)


def main():
    demo = EvaluationDemo()
    
    print("\n请选择评测模式:")
    print("  1. 模拟评测演示 (无需服务器)")
    print("  2. 真实评测流程 (需要启动服务器)")
    print("  3. 查看评测指南")
    
    choice = input("\n请输入选项 (1/2/3，默认 1): ").strip() or "1"
    
    if choice == "1":
        demo.demo_mock_evaluation()
    elif choice == "2":
        if demo.check_server():
            demo.run_real_evaluation()
        else:
            print("\n将为您展示模拟评测...")
            demo.demo_mock_evaluation()
    elif choice == "3":
        demo.show_evaluation_guide()
    else:
        print("无效选项，将显示模拟评测")
        demo.demo_mock_evaluation()


if __name__ == "__main__":
    main()
