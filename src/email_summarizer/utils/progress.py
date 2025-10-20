#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
进度计时器工具模块
提供实时进度显示和超时控制功能
"""
import sys
import time
import threading


class ProgressTimer:
    """实时进度计时器"""
    
    def __init__(self, timeout_seconds=60):
        """
        初始化进度计时器
        
        Args:
            timeout_seconds (int): 超时时间（秒），默认60秒
        """
        self.timeout_seconds = timeout_seconds
        self.start_time = None
        self.stop_event = threading.Event()
        self.timer_thread = None
        
    def start(self, message="处理中"):
        """
        开始计时器
        
        Args:
            message (str): 显示的处理消息
        """
        self.start_time = time.time()
        self.stop_event.clear()
        self.timer_thread = threading.Thread(target=self._update_timer, args=(message,))
        self.timer_thread.daemon = True
        self.timer_thread.start()
        
    def stop(self):
        """停止计时器"""
        if self.timer_thread:
            self.stop_event.set()
            self.timer_thread.join(timeout=1)
            # 清除当前行
            sys.stdout.write('\r' + ' ' * 80 + '\r')
            sys.stdout.flush()
            
    def _update_timer(self, message):
        """
        更新计时器显示
        
        Args:
            message (str): 显示的处理消息
        """
        while not self.stop_event.is_set():
            elapsed = time.time() - self.start_time
            remaining = max(0, self.timeout_seconds - elapsed)
            
            if remaining <= 0:
                sys.stdout.write(f'\r⏰ 超时！已等待 {elapsed:.1f}s')
                sys.stdout.flush()
                break
                
            # 简化显示：只显示经过时间和剩余时间
            sys.stdout.write(f'\r🔄 {message} - {elapsed:.1f}s (剩余 {remaining:.1f}s)')
            sys.stdout.flush()
            time.sleep(1.0)  # 减少更新频率
            
    def get_elapsed_time(self):
        """
        获取已经过的时间
        
        Returns:
            float: 已经过的时间（秒），如果未开始则返回0
        """
        if self.start_time is None:
            return 0
        return time.time() - self.start_time
        
    def is_timeout(self):
        """
        检查是否已超时
        
        Returns:
            bool: 是否已超时
        """
        if self.start_time is None:
            return False
        return self.get_elapsed_time() >= self.timeout_seconds