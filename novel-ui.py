import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import re
import sys
import requests
import json
import threading
import os
import time

class NovelReader:
    def __init__(self, root):
        self.root = root
        self.root.title("小说阅读器")
        root.tk.call('tk', 'scaling', 2)  # 将缩放比例设置为 2 倍

        # 启用高DPI支持（Windows 下可以尝试）
        if 'win' in sys.platform.lower():
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        self.chapters = {}
        self.current_file_path = None
        self.modification_direction = ""

        self.api_config = {
            "api_key": "",
            "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
            "model": "minimax-text-01",
            "temperature": 0.1,
            "top_p": 0.95,
            "max_tokens": 2048,
            "stream": True
        }

        self.toast_count = 0

        # 读取本地配置
        self.load_config()
        self.load_modification_direction()

        self.create_widgets()

    def create_widgets(self):
        self.left_frame = tk.Frame(self.root)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        self.left_scrollbar = tk.Scrollbar(self.left_frame, orient=tk.VERTICAL)
        self.left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.chapter_listbox = tk.Listbox(self.left_frame, width=10, height=30,
                                          yscrollcommand=self.left_scrollbar.set)
        self.chapter_listbox.pack(side=tk.LEFT, fill=tk.BOTH)
        self.chapter_listbox.bind('<<ListboxSelect>>', self.display_chapter_content)
        self.left_scrollbar.config(command=self.chapter_listbox.yview)

        self.right_frame = tk.Frame(self.root)
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.right_scrollbar = tk.Scrollbar(self.right_frame, orient=tk.VERTICAL)
        self.right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.chapter_text = tk.Text(self.right_frame, wrap=tk.WORD, font=("微软雅黑", 14),
                                    yscrollcommand=self.right_scrollbar.set)
        self.chapter_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.right_scrollbar.config(command=self.chapter_text.yview)

        self.load_button = tk.Button(self.root, text="加载小说", command=self.load_novel)
        self.load_button.pack(side=tk.BOTTOM, pady=5)
        
        self.delete_button = tk.Button(self.root, text="删除选中", command=self.delete_selected_text)
        self.delete_button.pack(side=tk.BOTTOM, pady=5)
        
        self.set_mod_button = tk.Button(self.root, text="修改方向", command=self.set_modification_direction)
        self.set_mod_button.pack(side=tk.BOTTOM, pady=5)
        
        self.modify_button = tk.Button(self.root, text="修改选中", command=self.modify_selected_text)
        self.modify_button.pack(side=tk.BOTTOM, pady=5)
        
        self.config_button = tk.Button(self.root, text="配置模型", command=self.config_model)
        self.config_button.pack(side=tk.BOTTOM, pady=5)

    def load_novel(self):
        file_path = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt")])
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                novel_text = f.read()
            self.current_file_path = file_path
        except Exception as e:
            messagebox.showerror("错误", f"无法读取文件: {str(e)}")
            return

        self.chapters = self.split_into_chapters(novel_text)
        self.chapter_listbox.delete(0, tk.END)
        for chap_title in self.chapters.keys():
            self.chapter_listbox.insert(tk.END, chap_title)

        # 默认显示第一章内容
        if self.chapter_listbox.size() > 0:
            self.chapter_listbox.selection_set(0)
            self.display_chapter_content(None)

    def split_into_chapters(self, text):
        pattern = r'(第[\d一二三四五六七八九十百千]+章)'
        parts = re.split(pattern, text)

        if not parts or len(parts) < 2:
            return {"全文": text}

        chapters = {}
        current_title = None
        current_content = []

        for item in parts:
            item = item.strip()
            if not item:
                continue
            if re.match(pattern, item):
                if current_title and current_content:
                    chapters[current_title] = "\n".join(current_content)
                current_title = item
                current_content = []
            else:
                current_content.append(item)

        if current_title and current_content:
            chapters[current_title] = "\n".join(current_content)

        return chapters

    def display_chapter_content(self, event):
        selected_index = self.chapter_listbox.curselection()
        if not selected_index:
            return
        selected_title = self.chapter_listbox.get(selected_index)
        content = self.chapters.get(selected_title, "")

        lines = content.splitlines()
        indented = ["　　" + ln for ln in lines]
        content_with_indent = "\n".join(indented)

        self.chapter_text.config(state=tk.NORMAL)
        self.chapter_text.delete(1.0, tk.END)
        self.chapter_text.insert(tk.END, content_with_indent)
        self.chapter_text.config(state=tk.DISABLED)

    # ================= 新增的“删除选中”功能 ==================
    def delete_selected_text(self):
        """
        1) 获取右侧文本框中用户选中的文本（去掉行首可能的全角空格）
        2) 在原 txt 文件中做一次替换操作：将选中的文本替换为空字符串
        3) 写回文件并重新加载
        """
        if not self.current_file_path:
            messagebox.showwarning("提示", "请先加载小说文件。")
            return

        # 先获取整段文本和选中部分
        self.chapter_text.config(state=tk.NORMAL)
        entire_text = self.chapter_text.get("1.0", tk.END).strip()
        try:
            selected_text = self.chapter_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected_text = ""
        self.chapter_text.config(state=tk.DISABLED)

        if not entire_text:
            messagebox.showwarning("提示", "右侧文本框中没有任何内容。")
            return
        if not selected_text.strip():
            messagebox.showwarning("提示", "请先在右侧文本框选中要删除的文本。")
            return

        # 读原文件内容
        try:
            with open(self.current_file_path, 'r', encoding='utf-8') as f:
                file_text = f.read()
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败：{str(e)}")
            return

        # 去除选中文本每行行首的“　　”
        def remove_leading_spaces(text):
            lines = text.splitlines(True)  # 保留换行符
            new_lines = []
            for ln in lines:
                if ln.startswith("　　"):
                    new_lines.append(ln[2:])
                else:
                    new_lines.append(ln)
            return "".join(new_lines)

        clean_selected = remove_leading_spaces(selected_text).strip('\r\n')
        if not clean_selected:
            messagebox.showwarning("提示", "无法识别要删除的文本（可能只选了缩进空格）。")
            return

        # 在文件内容中执行一次替换，count=1
        new_file_text = file_text.replace(clean_selected, "", 1)
        if new_file_text == file_text:
            # 没找到可替换的
            messagebox.showwarning("提示", "原文件中未找到选中的文本，删除失败。")
            return

        # 写回文件
        try:
            with open(self.current_file_path, 'w', encoding='utf-8') as f:
                f.write(new_file_text)
        except Exception as e:
            messagebox.showerror("错误", f"写入文件失败：{str(e)}")
            return

        # 重新加载
        self.reload_current_file()


    def set_modification_direction(self):
        self.load_modification_direction()

        direction_dialog = tk.Toplevel(self.root)
        direction_dialog.title("修改方向")

        label = tk.Label(direction_dialog, text="请输入对文本修改的方向（提示词）：")
        label.pack(pady=5)

        text_box = tk.Text(direction_dialog, width=80, height=20, font=("微软雅黑", 12))
        text_box.pack(padx=10, pady=5)
        text_box.insert("1.0", self.modification_direction)

        def on_confirm():
            user_input = text_box.get("1.0", tk.END).strip()
            self.modification_direction = user_input
            self.save_modification_direction()
            direction_dialog.destroy()

        confirm_button = tk.Button(direction_dialog, text="确定", command=on_confirm)
        confirm_button.pack(pady=5)

        direction_dialog.transient(self.root)
        direction_dialog.grab_set()
        direction_dialog.wait_window()

    def modify_selected_text(self):
        self.chapter_text.config(state=tk.NORMAL)
        entire_text = self.chapter_text.get("1.0", tk.END).strip()

        try:
            selected_text = self.chapter_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected_text = ""
        self.chapter_text.config(state=tk.DISABLED)

        if not entire_text:
            messagebox.showwarning("提示", "右侧文本框没有内容。")
            return
        if not selected_text.strip():
            messagebox.showwarning("提示", "请先在右侧文本框中选中要修改的内容。")
            return

        file_path = os.path.join(os.path.dirname(sys.argv[0]), "修改方向.txt")
        temp_direction_text = ""
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    temp_direction_text = f.read().strip()
            except:
                pass

        direction_dialog = tk.Toplevel(self.root)
        direction_dialog.title("编辑修改方向")

        label = tk.Label(direction_dialog, text="当前修改方向（可编辑，仅本次有效）：")
        label.pack(pady=5)

        dir_box = tk.Text(direction_dialog, width=80, height=20, font=("微软雅黑", 12))
        dir_box.pack(padx=10, pady=5)
        dir_box.insert("1.0", temp_direction_text)

        def on_next():
            local_mod_dir = dir_box.get("1.0", tk.END).strip()
            direction_dialog.destroy()

            prompt = (
                f"以下是本章内容（仅供参考）：\n\n"
                f"{entire_text}\n\n"
                f"现在请对我选中的这部分文本进行改写或润色：\n\n"
                f"【修改方向】{local_mod_dir}\n\n"
                f"【待修改文本】\n{selected_text}\n"
            )

            def on_complete(result):
                if result is None:
                    return
                self.show_compare_dialog(original_text=selected_text, modified_text=result)

            self.call_api_in_thread(prompt, on_complete)

        next_button = tk.Button(direction_dialog, text="下一步", command=on_next)
        next_button.pack(pady=5)

        direction_dialog.transient(self.root)
        direction_dialog.grab_set()
        direction_dialog.wait_window()

    def show_compare_dialog(self, original_text, modified_text):
        compare_win = tk.Toplevel(self.root)
        compare_win.title("对比显示（选中内容）")
        try:
            compare_win.state("zoomed")
        except:
            compare_win.geometry("1200x800")

        compare_paned = tk.PanedWindow(compare_win, orient=tk.HORIZONTAL)
        compare_paned.pack(fill=tk.BOTH, expand=True)

        left_frame = tk.Frame(compare_paned)
        right_frame = tk.Frame(compare_paned)
        compare_paned.add(left_frame, stretch="always")
        compare_paned.add(right_frame, stretch="always")

        scroll_left = tk.Scrollbar(left_frame, orient=tk.VERTICAL)
        scroll_left.pack(side=tk.RIGHT, fill=tk.Y)

        text_orig = tk.Text(left_frame, wrap=tk.WORD, font=("微软雅黑", 12),
                            yscrollcommand=scroll_left.set)
        text_orig.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_left.config(command=text_orig.yview)

        scroll_right = tk.Scrollbar(right_frame, orient=tk.VERTICAL)
        scroll_right.pack(side=tk.RIGHT, fill=tk.Y)

        text_mod = tk.Text(right_frame, wrap=tk.WORD, font=("微软雅黑", 12),
                           yscrollcommand=scroll_right.set)
        text_mod.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_right.config(command=text_mod.yview)

        text_orig.insert(tk.END, original_text)
        text_mod.insert(tk.END, modified_text)

        bottom_frame = tk.Frame(compare_win)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        orig_len = len(original_text)
        mod_len = len(modified_text)
        info_label = tk.Label(
            bottom_frame,
            text=f"原文字数: {orig_len}   |   修改后字数: {mod_len}"
        )
        info_label.pack(side=tk.LEFT, padx=10)

        def save_and_close():
            """
            先调用原有的保存逻辑，然后关闭对比窗口。
            """
            self.save_modified_selection(original_text, modified_text)
            # 如果 save_modified_selection 执行时没有出错或中途 return，就关闭窗口
            compare_win.destroy()

        save_button = tk.Button(
            bottom_frame,
            text="保存修改结果",
            command=save_and_close
        )
        save_button.pack(side=tk.RIGHT, padx=10)

    def save_modified_selection(self, original_text, modified_text):

        if not self.current_file_path:
            messagebox.showwarning("提示", "未记录小说文件名，请先加载小说文件。")
            return

        # 1) 读出源文件的全部文本
        try:
            with open(self.current_file_path, 'r', encoding='utf-8') as f:
                file_text = f.read()
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败：{str(e)}")
            return

        # 2) 去掉行首的 "　　"
        def remove_leading_spaces(text):
            lines = text.splitlines(True)
            new_lines = []
            for ln in lines:
                if ln.startswith("　　"):
                    new_lines.append(ln[2:])
                else:
                    new_lines.append(ln)
            return "".join(new_lines)

        clean_original = remove_leading_spaces(original_text).strip('\r\n')
        clean_modified = remove_leading_spaces(modified_text).rstrip('\r\n')

        if not clean_original:
            messagebox.showwarning("提示", "无法识别要替换的原文内容（可能只选了缩进空格）。")
            return

        # 3) 拼接新的替换片段
        replaced_block = (
            f"---------------------------{clean_original}(原文内容，不要参考这一块的内容)---------------------------\n"
            f"---------------------------{clean_modified}(重写内容，需要参考这一块的内容)---------------------------"
        )

        # 4) 执行一次性替换
        new_file_text = file_text.replace(clean_original, replaced_block, 1)
        if new_file_text == file_text:
            messagebox.showwarning("提示", "未能在原文件中找到选中的文本，替换失败。")
            return

        # 5) 写回文件
        try:
            with open(self.current_file_path, 'w', encoding='utf-8') as f:
                f.write(new_file_text)
        except Exception as e:
            messagebox.showerror("错误", f"写入文件失败：{str(e)}")
            return

        # 6) 重新加载
        self.reload_current_file()

    def reload_current_file(self):
        """
        不弹对话框，直接按 self.current_file_path 重新加载文件
        """
        if not self.current_file_path:
            return
        try:
            with open(self.current_file_path, 'r', encoding='utf-8') as f:
                novel_text = f.read()
            self.chapters = self.split_into_chapters(novel_text)
        except Exception as e:
            messagebox.showerror("错误", f"重新加载文件失败: {str(e)}")
            return

        # 刷新左侧章节列表
        self.chapter_listbox.delete(0, tk.END)
        for chap_title in self.chapters.keys():
            self.chapter_listbox.insert(tk.END, chap_title)
        # 默认选中并显示第一章
        if self.chapter_listbox.size() > 0:
            self.chapter_listbox.selection_set(0)
            self.display_chapter_content(None)

    # ========== 以下为原先的配置 / 调用模型等函数 ==========

    def config_model(self):
        config_win = tk.Toplevel(self.root)
        config_win.title("配置大模型")

        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()

        new_x = root_x + root_width - 999
        new_y = root_y + root_height - 666
        config_win.geometry(f"+{new_x}+{new_y}")

        row = 0

        tk.Label(config_win, text="API Key:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
        api_key_entry = tk.Entry(config_win, width=50)
        api_key_entry.grid(row=row, column=1, padx=5, pady=5)
        api_key_entry.insert(0, self.api_config["api_key"])
        row += 1

        tk.Label(config_win, text="URL:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
        url_entry = tk.Entry(config_win, width=50)
        url_entry.grid(row=row, column=1, padx=5, pady=5)
        url_entry.insert(0, self.api_config["url"])
        row += 1

        tk.Label(config_win, text="Model:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
        model_entry = tk.Entry(config_win, width=50)
        model_entry.grid(row=row, column=1, padx=5, pady=5)
        model_entry.insert(0, self.api_config["model"])
        row += 1

        tk.Label(config_win, text="Temperature:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
        temp_entry = tk.Entry(config_win, width=10)
        temp_entry.grid(row=row, column=1, padx=5, pady=5, sticky="w")
        temp_entry.insert(0, str(self.api_config["temperature"]))
        row += 1

        tk.Label(config_win, text="Top_p:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
        topp_entry = tk.Entry(config_win, width=10)
        topp_entry.grid(row=row, column=1, padx=5, pady=5, sticky="w")
        topp_entry.insert(0, str(self.api_config["top_p"]))
        row += 1

        tk.Label(config_win, text="max_tokens:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
        max_tokens_entry = tk.Entry(config_win, width=10)
        max_tokens_entry.grid(row=row, column=1, padx=5, pady=5, sticky="w")
        max_tokens_entry.insert(0, str(self.api_config["max_tokens"]))
        row += 1

        tk.Label(config_win, text="Stream:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
        stream_var = tk.BooleanVar(value=self.api_config["stream"])
        stream_checkbox = tk.Checkbutton(config_win, variable=stream_var)
        stream_checkbox.grid(row=row, column=1, padx=5, pady=5, sticky="w")
        row += 1

        def save_config():
            self.api_config["api_key"] = api_key_entry.get().strip()
            self.api_config["url"] = url_entry.get().strip()
            self.api_config["model"] = model_entry.get().strip()

            try:
                self.api_config["temperature"] = float(temp_entry.get().strip())
            except ValueError:
                self.api_config["temperature"] = 0.1

            try:
                self.api_config["top_p"] = float(topp_entry.get().strip())
            except ValueError:
                self.api_config["top_p"] = 0.95

            try:
                self.api_config["max_tokens"] = int(max_tokens_entry.get().strip())
            except ValueError:
                self.api_config["max_tokens"] = 2048

            self.api_config["stream"] = stream_var.get()
            self.save_config()

            messagebox.showinfo("提示", "配置已保存！")
            config_win.destroy()

        save_button = tk.Button(config_win, text="保存配置", command=save_config)
        save_button.grid(row=row, columnspan=2, pady=10)

    def call_api_in_thread(self, prompt, callback):
        def task():
            self.toast_count = 0
            result = self.call_api(prompt)
            self.root.after(0, lambda: callback(result))
        t = threading.Thread(target=task)
        t.daemon = True
        t.start()

    def call_api(self, prompt):
        if not self.api_config["api_key"]:
            self.show_error("请先在【配置模型】中设置 API Key。")
            return None

        payload = {
            "model": self.api_config["model"],
            "messages": [
                {
                    "content": prompt,
                    "role": "user",
                    "name": "用户"
                }
            ],
            "stream": self.api_config["stream"],
            "max_tokens": self.api_config["max_tokens"],
            "temperature": self.api_config["temperature"],
            "top_p": self.api_config["top_p"]
        }
        headers = {
            "Authorization": f"Bearer {self.api_config['api_key']}",
            "Content-Type": "application/json"
        }

        try:
            if self.api_config["stream"]:
                response = requests.post(
                    self.api_config["url"],
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=60
                )
                if response.status_code != 200:
                    self.show_error(f"HTTP错误：{response.status_code}\n{response.text}")
                    return None

                all_text = ""
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        text_chunk = chunk.decode('utf-8', errors='ignore').strip()
                        for line in text_chunk.splitlines():
                            line = line.strip()
                            if line.startswith("data: "):
                                line_content = line[len("data: "):]
                                if line_content in ["[DONE]", ""]:
                                    continue
                                try:
                                    data = json.loads(line_content)
                                    if "choices" in data and len(data["choices"]) > 0:
                                        choice = data["choices"][0]
                                        if "delta" in choice and "content" in choice["delta"]:
                                            chunk_text = choice["delta"]["content"]
                                        elif "message" in choice and "content" in choice["message"]:
                                            chunk_text = choice["message"]["content"]
                                        else:
                                            chunk_text = ""
                                        if chunk_text:
                                            all_text += chunk_text
                                            self.root.after(
                                                0,
                                                lambda text=chunk_text: self.show_toast(text)
                                            )
                                except json.JSONDecodeError:
                                    pass
                return all_text
            else:
                response = requests.post(
                    self.api_config["url"],
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                if response.status_code != 200:
                    self.show_error(f"HTTP错误：{response.status_code}\n{response.text}")
                    return None

                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        return choice["message"]["content"]
                    elif "delta" in choice and "content" in choice["delta"]:
                        return choice["delta"]["content"]
                return "（未获取到内容）"
        except Exception as e:
            self.show_error(f"调用接口出错：{str(e)}")
            return None

    def show_error(self, msg):
        self.root.after(0, lambda: messagebox.showerror("错误", msg))

    def load_config(self):
        config_path = os.path.join(os.path.dirname(sys.argv[0]), "model_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    if k in self.api_config:
                        self.api_config[k] = v
            except Exception as e:
                print("读取配置文件出错：", e)

    def save_config(self):
        config_path = os.path.join(os.path.dirname(sys.argv[0]), "model_config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.api_config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("保存配置文件出错：", e)

    def load_modification_direction(self):
        file_path = os.path.join(os.path.dirname(sys.argv[0]), "修改方向.txt")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.modification_direction = f.read().strip()
            except:
                pass

    def save_modification_direction(self):
        file_path = os.path.join(os.path.dirname(sys.argv[0]), "修改方向.txt")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.modification_direction)
        except:
            pass

    def show_toast(self, message, duration=2000):
        self.toast_count += 1
        display_message = f"这是第{self.toast_count}个toast: {message}"

        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)

        self.root.update_idletasks()
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()

        label = tk.Label(toast, text=display_message, font=("微软雅黑", 10), bg="black", fg="white", padx=10, pady=5)
        label.pack()
        toast.update_idletasks()

        toast_w = toast.winfo_width()
        toast_h = toast.winfo_height()

        x = root_x + root_w - toast_w - 233
        y = root_y + root_h - toast_h - 233
        toast.geometry(f"{toast_w}x{toast_h}+{x}+{y}")

        toast.after(duration, toast.destroy)


if __name__ == "__main__":
    root = tk.Tk()
    app = NovelReader(root)
    try:
        root.state('zoomed')
    except:
        root.geometry("1200x800")
    root.mainloop()
