#!/usr/bin/env python3
"""
测试无干扰情况下的仿真功能
"""
import sys
sys.path.insert(0, '.')

from unified_framework import run_simulation, UnifiedFramework

# 自定义雷达参数
custom_radar_params = {
    'f0': 15e6,
    'Bw': 5e6,
    'Pw': 20e-6,
    'Fs': 50e6,
    'target_dist': 6000,
    'jammer_amp': 8.0
}

print("测试无干扰情况 (jammer_type=None) vs WLN 抗干扰...")
try:
    results = run_simulation(
        jammer_type=None,
        antijam_type='WLN',
        radar_params=custom_radar_params,
        antijam_kwargs={'par1': 2.5, 'par2': 6}
    )
    
    # 打印摘要
    framework = UnifiedFramework(None, 'WLN', custom_radar_params)
    framework.results = results
    print(framework.get_summary())
    
    # 测试可视化
    print("\n生成无干扰可视化图表...")
    try:
        framework.visualize(save_path='./test_no_jammer.png', show_plot=False)
        print("图表保存成功: test_no_jammer.png")
    except Exception as e:
        print(f"可视化失败: {e}")
        
except Exception as e:
    print(f"无干扰测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试无干扰情况 (jammer_type='NoJammer') vs WLN 抗干扰...")
try:
    results = run_simulation(
        jammer_type='NoJammer',
        antijam_type='WLN',
        radar_params=custom_radar_params,
        antijam_kwargs={'par1': 2.5, 'par2': 6}
    )
    
    # 打印摘要
    framework = UnifiedFramework('NoJammer', 'WLN', custom_radar_params)
    framework.results = results
    print(framework.get_summary())
    
    # 测试可视化
    print("\n生成无干扰可视化图表...")
    try:
        framework.visualize(save_path='./test_NoJammer.png', show_plot=False)
        print("图表保存成功: test_NoJammer.png")
    except Exception as e:
        print(f"可视化失败: {e}")
        
except Exception as e:
    print(f"NoJammer测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试完成！")