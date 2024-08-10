import datetime
import json
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import pygame
import requests
from tkcalendar import Calendar


class AudioPlayer:
    def __init__(self, root):

        self.debug_mode = False
        self.root = root
        self.root.title("自动播放听力系统")

        # 初始化音频播放模块
        pygame.mixer.init()

        # 存储播放计划和节假日
        self.schedules = []
        self.holidays = []

        self.schedule_lock = threading.Lock()  # 初始化锁
        self.schedule_event = threading.Event()  # 用于通知调度线程
        self.thread_running = False
        self.kill_thread = False

        # 加载保存的数据
        self.load_data()
        self.get_holiday()
        # 根据配置文件的调试标志决定是否隐藏主窗口
        if not self.debug_mode:
            self.root.withdraw()

        self.schedules = [s for s in self.schedules if not self.is_schedule_expired(s)]  # 删除过期日程

        # 日历选择器
        self.cal = Calendar(root, selectmode='day', date_pattern='yyyy-mm-dd', mindate=datetime.date.today())
        self.cal.grid(row=0, column=0, padx=10, pady=10)

        self.highlight_holidays()

        # 时间选择器
        self.time_label = tk.Label(root, text="选择时间 (HH:MM):")
        self.time_label.grid(row=1, column=0, padx=10, pady=10)

        self.time_entry = tk.Entry(root)
        self.time_entry.grid(row=1, column=1, padx=10, pady=10)

        # 音频文件选择按钮
        self.audio_file_label = tk.Label(root, text="选择音频文件:")
        self.audio_file_label.grid(row=2, column=0, padx=10, pady=10)

        self.audio_file_button = tk.Button(root, text="浏览...", command=self.select_audio_file)
        self.audio_file_button.grid(row=2, column=1, padx=10, pady=10)

        # 选择节假日按钮
        self.holiday_button = tk.Button(root, text="设置节假日...", command=self.set_holidays)
        self.holiday_button.grid(row=3, column=0, padx=10, pady=10)

        # 添加播放计划按钮
        self.add_schedule_button = tk.Button(root, text="添加播放计划", command=self.add_schedule)
        self.add_schedule_button.grid(row=3, column=1, padx=10, pady=10)

        # 显示播放计划
        self.schedule_list = tk.Listbox(root, width=50, height=10)
        self.schedule_list.grid(row=4, column=0, columnspan=2, padx=10, pady=10)

        # 删除播放计划按钮
        self.delete_schedule_button = tk.Button(root, text="删除选中计划", command=self.delete_schedule)
        self.delete_schedule_button.grid(row=5, column=0, columnspan=2, padx=10, pady=10)

        # 显示已保存的播放计划并启动播放线程
        self.display_schedules()
        self.start_scheduler_thread()

        logging.basicConfig(filename='scheduler.log', level=logging.INFO,
                            format='%(asctime)s - %(filename)s - %(funcName)s - %(levelname)s - %(message)s')

        # 绑定关闭事件到自定义函数
        root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def select_audio_file(self):
        self.audio_file = filedialog.askopenfilename(title="选择音频文件", filetypes=[("Audio Files", "*.mp3 *.wav")])
        self.audio_file_label.config(text=os.path.basename(self.audio_file))

    def set_holidays(self):
        holidays_win = tk.Toplevel(self.root)
        holidays_win.title("设置节假日")

        self.holiday_calendar = Calendar(holidays_win, selectmode='day', date_pattern='yyyy-mm-dd')
        self.holiday_calendar.pack(padx=10, pady=10)

        add_holiday_button = tk.Button(holidays_win, text="添加节假日", command=self.add_holiday)
        add_holiday_button.pack(pady=10)

    def add_holiday(self):
        selected_date = self.holiday_calendar.get_date()
        if selected_date not in self.holidays:
            self.holidays.append(selected_date)
            self.highlight_holidays()
            messagebox.showinfo("成功", f"{selected_date} 已被添加为节假日")
            self.save_data()

    def highlight_holidays(self):
        for holiday in self.holidays:
            self.cal.calevent_create(datetime.datetime.strptime(holiday, '%Y-%m-%d'), 'Holiday', 'holiday')
        self.cal.tag_config('holiday', background='yellow', foreground='black')

    def add_schedule(self):
        selected_date = self.cal.get_date()
        selected_time = self.time_entry.get()
        # 检查日期和时间格式的合法性
        try:
            scheduled_datetime = datetime.datetime.strptime(f"{selected_date} {selected_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            messagebox.showwarning("时间格式错误", "请输入合法的时间格式，例如 14:30")
            return

        # 检查时间是否是未来时间
        now = datetime.datetime.now()
        if scheduled_datetime <= now:
            messagebox.showwarning("时间错误", "请选择一个未来的时间")
            return
        if selected_date in self.holidays:
            messagebox.showwarning("节假日", f"{selected_date} 是节假日，无法添加播放计划")
            return
        if not selected_time:
            messagebox.showwarning("时间未设置", "请设置播放时间")
            return
        if not hasattr(self, 'audio_file'):
            messagebox.showwarning("音频文件未选择", "请选择音频文件")
            return

        schedule = {"date": selected_date, "time": selected_time, "audio": self.audio_file}

        with self.schedule_lock:  # 锁定
            self.schedules.append(schedule)
            self.schedules.sort(key=lambda x: f"{x['date']} {x['time']}")  # 确保日程按时间排序
            self.save_data()
            self.display_schedules()

            # 如果新添加的日程是第一个，通知调度线程
            if self.schedules[0] == schedule:
                if self.thread_running:
                    self.kill_scheduler_thread()
                    self.start_scheduler_thread()
                    logging.info("Refresh thread")
                else:
                    self.start_scheduler_thread()
                    logging.info("Start thread")

    def delete_schedule(self):
        selected_index = self.schedule_list.curselection()
        if selected_index:
            with self.schedule_lock:  # 锁定
                if selected_index[0] == 0:
                    if self.thread_running:
                        self.kill_scheduler_thread()
                        self.start_scheduler_thread()
                        logging.info("Refresh thread")

                del self.schedules[selected_index[0]]
                self.save_data()
                self.display_schedules()
        else:
            messagebox.showwarning("未选择", "请选择要删除的计划")

    def save_data(self):
        # 保存播放计划和节假日到文件
        data = {
            'schedules': self.schedules,
            'debug': self.debug_mode,
            'holidays': {str(datetime.datetime.now().year): self.holidays}
        }
        with open('audio_scheduler_data.json', 'w') as f:
            json.dump(data, f)

    def load_data(self):
        # 加载已保存的数据
        if os.path.exists('audio_scheduler_data.json'):
            with open('audio_scheduler_data.json', 'r') as f:
                data = json.load(f)
                self.schedules = data.get('schedules', [])
                self.holidays = data['holidays'].get(str(datetime.datetime.now().year), [])
                self.debug_mode = data.get('debug', False)

    def display_schedules(self):
        # 清空列表并重新显示已保存的播放计划
        self.schedule_list.delete(0, tk.END)
        for schedule in self.schedules:
            self.schedule_list.insert(tk.END,
                                      f"{schedule['date']} {schedule['time']} - {os.path.basename(schedule['audio'])}")

    def is_schedule_expired(self, schedule):
        scheduled_datetime = datetime.datetime.strptime(f"{schedule['date']} {schedule['time']}", "%Y-%m-%d %H:%M")
        return scheduled_datetime < datetime.datetime.now()

    def start_scheduler_thread(self):
        # 使用单一线程管理所有播放任务
        threading.Thread(target=self.scheduler).start()

    def kill_scheduler_thread(self):
        self.kill_thread = True
        self.schedule_event.set()

    def scheduler(self):
        self.thread_running = True
        logging.info("Start thread")
        with self.schedule_lock:  # 锁定
            if not self.schedules:
                self.thread_running = False
                return
            now = datetime.datetime.now()
            next_schedule = self.schedules[0]
            scheduled_datetime = datetime.datetime.strptime(f"{next_schedule['date']} {next_schedule['time']}",
                                                            "%Y-%m-%d %H:%M")

        time_to_wait = (scheduled_datetime - now).total_seconds()
        logging.info("time wait")

        # 等待直到下一个日程时间，或等待新的日程添加
        self.schedule_event.wait(timeout=time_to_wait)
        self.schedule_event.clear()

        if self.kill_thread:
            self.kill_thread = False
            self.thread_running = False
            return

        with self.schedule_lock:  # 再次锁定
            pygame.mixer.music.load(next_schedule["audio"])
            pygame.mixer.music.play()

        # 等待音频播放完成
        while pygame.mixer.music.get_busy():
            time.sleep(1)

        with self.schedule_lock:
            # 删除已经播放的日程
            self.schedules.pop(0)
            self.save_data()
            self.display_schedules()

        self.start_scheduler_thread()

    def on_closing(self):
        if messagebox.askokcancel("退出", "确定关闭吗"):
            self.kill_scheduler_thread()
            self.root.destroy()

    def get_holiday(self):
        if self.holidays:
            return

        url = "https://www.shuyz.com/githubfiles/china-holiday-calender/master/holidayAPI.json"

        # Fetch the JSON data from the URL
        response = requests.get(url)
        data = response.json()

        # Extract holidays for 2024
        holidays = []
        for holiday in data['Years'][str(datetime.datetime.now().year)]:

            # Define the start and end dates
            start_date = datetime.datetime.strptime(holiday['StartDate'], "%Y-%m-%d")
            end_date = datetime.datetime.strptime(holiday['EndDate'], "%Y-%m-%d")

            current_date = start_date
            while current_date <= end_date:
                holidays.append(current_date.strftime("%Y-%m-%d"))
                current_date += datetime.timedelta(days=1)
        self.holidays = holidays

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioPlayer(root)
    root.mainloop()

#pyinstaller -F -w main.py --hidden-import=babel.numbers
