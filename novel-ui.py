import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import re
import sys
import requests
import json
import threading
import os
import time
from tkinter import ttk  # 用于Notebook

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
        self.modification_direction = ""  # 旧版使用，目前保留兼容
        # 用于记录上次加载时的章节索引与文本框滚动位置
        self.last_chapter_index = None
        self.last_scroll_fraction = None

        # ---------------- 大模型配置信息 ----------------
        self.model_configs = {}
        self.current_model_name = "小说模型"  # 默认使用“小说模型”
        self.load_model_configs()  # 尝试从文件中加载配置

        # 旧版的修改方向（单一文本）文件（兼容），现已用列表管理
        self.load_modification_direction()
        # 新增：加载修改方向列表（存储于 JSON 文件中）
        self.modification_directions = []
        self.load_modification_directions_list()

        self.toast_window = None
        self.toast_timer = None

        self.create_widgets()

    def create_widgets(self):
        # 顶部统一菜单栏：左侧为模型选择及当前文件显示，右侧为各功能按钮
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        # 左侧：模型选择区域及当前文件名显示
        model_frame = tk.Frame(top_frame)
        model_frame.pack(side=tk.LEFT)
        tk.Label(model_frame, text="当前模型:").pack(side=tk.LEFT)
        self.model_option = tk.StringVar(value=self.current_model_name)
        model_names = list(self.model_configs.keys())
        option_menu = tk.OptionMenu(model_frame, self.model_option, *model_names, command=self.change_model)
        option_menu.pack(side=tk.LEFT, padx=5)
        # 显示当前加载的文件名
        self.file_label = tk.Label(model_frame, text="未加载文件", fg="blue")
        self.file_label.pack(side=tk.LEFT, padx=10)

        # 右侧：所有功能按钮
        menu_buttons_frame = tk.Frame(top_frame)
        menu_buttons_frame.pack(side=tk.RIGHT)
        self.load_button = tk.Button(menu_buttons_frame, text="加载小说", command=self.load_novel)
        self.load_button.pack(side=tk.LEFT, padx=5)
        self.set_mod_button = tk.Button(menu_buttons_frame, text="修改方向", command=self.set_modification_direction)
        self.set_mod_button.pack(side=tk.LEFT, padx=5)
        self.modify_button = tk.Button(menu_buttons_frame, text="修改选中（调用API）", command=self.modify_selected_text)
        self.modify_button.pack(side=tk.LEFT, padx=5)
        # 将原“保存修改内容”按钮改为“直接编辑本章”
        self.edit_chapter_button = tk.Button(menu_buttons_frame, text="直接编辑本章", command=self.edit_current_chapter)
        self.edit_chapter_button.pack(side=tk.LEFT, padx=5)
        self.config_button = tk.Button(menu_buttons_frame, text="配置模型", command=self.config_model)
        self.config_button.pack(side=tk.LEFT, padx=5)

        # 左侧章节列表
        self.left_frame = tk.Frame(self.root)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        self.left_scrollbar = tk.Scrollbar(self.left_frame, orient=tk.VERTICAL)
        self.left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chapter_listbox = tk.Listbox(self.left_frame, width=20, height=30,
                                          yscrollcommand=self.left_scrollbar.set)
        self.chapter_listbox.pack(side=tk.LEFT, fill=tk.BOTH)
        self.chapter_listbox.bind('<<ListboxSelect>>', self.display_chapter_content)
        self.left_scrollbar.config(command=self.chapter_listbox.yview)

        # 右侧文本显示区（用于显示，但禁止编辑）
        self.right_frame = tk.Frame(self.root)
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.right_scrollbar = tk.Scrollbar(self.right_frame, orient=tk.VERTICAL)
        self.right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chapter_text = tk.Text(self.right_frame, wrap=tk.WORD, font=("思源黑体", 14))
        self.chapter_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chapter_text.config(yscrollcommand=self.right_scrollbar.set)
        self.right_scrollbar.config(command=self.chapter_text.yview)
        # 禁止在主界面直接编辑，但仍允许光标移动和选中
        self.chapter_text.bind("<Key>", lambda e: "break")

    def change_model(self, value):
        self.current_model_name = value

    def load_novel(self):
        # 如果当前已有文件，则先保存当前的章节索引和滚动位置
        old_file = self.current_file_path
        if old_file is not None:
            sel = self.chapter_listbox.curselection()
            self.last_chapter_index = sel[0] if sel else 0
            self.last_scroll_fraction = self.chapter_text.yview()[0]
        file_path = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt")])
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                novel_text = f.read()
            self.current_file_path = file_path
            self.file_label.config(text="当前文件: " + os.path.basename(file_path))
        except Exception as e:
            messagebox.showerror("错误", f"无法读取文件: {str(e)}")
            return

        self.chapters = self.split_into_chapters(novel_text)
        self.chapter_listbox.delete(0, tk.END)
        for chap_title in self.chapters.keys():
            self.chapter_listbox.insert(tk.END, chap_title)

        # 如果重新加载的是同一个文件且有之前的进度，则恢复
        if file_path == old_file and self.last_chapter_index is not None:
            chapter_index = self.last_chapter_index
            if chapter_index >= self.chapter_listbox.size():
                chapter_index = 0
            self.chapter_listbox.selection_clear(0, tk.END)
            self.chapter_listbox.selection_set(chapter_index)
            self.display_chapter_content(None)
            if self.last_scroll_fraction is not None:
                self.chapter_text.yview_moveto(self.last_scroll_fraction)
        else:
            # 否则默认显示第一章
            if self.chapter_listbox.size() > 0:
                self.chapter_listbox.selection_clear(0, tk.END)
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
                if current_title is not None and current_content:
                    chapters[current_title] = "\n".join(current_content)
                current_title = item
                current_content = []
            else:
                current_content.append(item)
        if current_title is not None and current_content:
            chapters[current_title] = "\n".join(current_content)
        return chapters

    def display_chapter_content(self, event):
        sel = self.chapter_listbox.curselection()
        if not sel:
            return
        selected_title = self.chapter_listbox.get(sel)
        content = self.chapters.get(selected_title, "")
        # 自动添加缩进（保存时会去除）
        lines = content.splitlines()
        indented = ["　　" + ln for ln in lines]
        content_with_indent = "\n".join(indented)
        # 允许取回文本前先临时设置为 normal
        self.chapter_text.config(state=tk.NORMAL)
        self.chapter_text.delete(1.0, tk.END)
        self.chapter_text.insert(tk.END, content_with_indent)
        # 显示后禁止编辑（但允许光标移动和选中）
        self.chapter_text.config(state=tk.DISABLED)

    # --------------- 修改方向管理（列表模式） ---------------
    def set_modification_direction(self):
        """弹出管理修改方向列表的窗口，支持新建、编辑、删除条目，并可存储到本地"""
        win = tk.Toplevel(self.root)
        win.title("管理修改方向")
        win.geometry("600x300")
        # 列表框显示所有修改方向
        listbox = tk.Listbox(win, width=80, height=10)
        listbox.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        for item in self.modification_directions:
            listbox.insert(tk.END, item)
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=5)
        def add_direction():
            new_win = tk.Toplevel(win)
            new_win.title("新建修改方向")
            txt = tk.Text(new_win, width=60, height=10, font=("思源黑体", 12))
            txt.pack(padx=10, pady=10)
            new_win.grab_set()
            def on_add():
                content = txt.get("1.0", tk.END).strip()
                if content:
                    self.modification_directions.append(content)
                    listbox.insert(tk.END, content)
                new_win.destroy()
            tk.Button(new_win, text="确定", command=on_add).pack(pady=5)
        def edit_direction():
            try:
                idx = listbox.curselection()[0]
            except IndexError:
                messagebox.showwarning("提示", "请先选中一条修改方向进行编辑。")
                return
            current_text = self.modification_directions[idx]
            edit_win = tk.Toplevel(win)
            edit_win.title("编辑修改方向")
            txt = tk.Text(edit_win, width=60, height=10, font=("思源黑体", 12))
            txt.pack(padx=10, pady=10)
            txt.insert("1.0", current_text)
            edit_win.grab_set()
            def on_edit():
                content = txt.get("1.0", tk.END).strip()
                if content:
                    self.modification_directions[idx] = content
                    listbox.delete(idx)
                    listbox.insert(idx, content)
                edit_win.destroy()
            tk.Button(edit_win, text="确定", command=on_edit).pack(pady=5)
        def delete_direction():
            try:
                idx = listbox.curselection()[0]
            except IndexError:
                messagebox.showwarning("提示", "请先选中一条修改方向进行删除。")
                return
            if messagebox.askyesno("确认", "确定删除选中的修改方向吗？"):
                listbox.delete(idx)
                del self.modification_directions[idx]
        tk.Button(btn_frame, text="新建", command=add_direction).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="编辑", command=edit_direction).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="删除", command=delete_direction).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="存储", command=lambda: (self.save_modification_directions_list(),
                                                           messagebox.showinfo("提示", "修改方向已保存！"))).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="关闭", command=win.destroy).pack(side=tk.LEFT, padx=5)
        win.transient(self.root)
        win.wait_window()

    def load_modification_directions_list(self):
        """从 '修改方向.json' 中加载修改方向列表（每一项为一条文本）"""
        file_path = os.path.join(os.path.dirname(sys.argv[0]), "修改方向.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.modification_directions = json.load(f)
            except Exception as e:
                print("读取修改方向配置出错：", e)
                self.modification_directions = []
        else:
            self.modification_directions = []

    def save_modification_directions_list(self):
        """将修改方向列表保存到 '修改方向.json' 文件中"""
        file_path = os.path.join(os.path.dirname(sys.argv[0]), "修改方向.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.modification_directions, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("保存修改方向配置出错：", e)

    # 旧版的修改方向加载/保存（兼容）
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

    # --------------- 编辑本章功能（直接编辑当前章节） ---------------
    def edit_current_chapter(self):
        # 获取当前显示的文本内容和滚动位置
        current_text = self.chapter_text.get("1.0", tk.END)
        current_scroll = self.chapter_text.yview()[0]
        # 去除每行前的缩进（即移除“　　”）
        def remove_indent(text):
            lines = text.splitlines()
            return "\n".join([ln[2:] if ln.startswith("　　") else ln for ln in lines])
        clean_text = remove_indent(current_text).rstrip("\n")
        # 获取当前章节索引
        try:
            chapter_index = self.chapter_listbox.curselection()[0]
        except IndexError:
            chapter_index = 0

        # 弹出全屏编辑对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑本章")
        dialog.wm_state('zoomed')
        text_widget = tk.Text(dialog, wrap=tk.WORD, font=("思源黑体", 14))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert("1.0", clean_text)
        text_widget.update_idletasks()
        text_widget.yview_moveto(current_scroll)
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=5)
        def on_cancel():
            dialog.destroy()
        def on_save():
            edited = text_widget.get("1.0", tk.END)
            # 更新当前章节内容
            chapter_title = self.chapter_listbox.get(chapter_index)
            self.chapters[chapter_title] = edited.rstrip("\n")
            # 重构全文内容并直接写回当前文件
            full_text = ""
            for title in self.chapter_listbox.get(0, tk.END):
                content = self.chapters.get(title, "")
                full_text += title + "\n" + content + "\n\n"
            try:
                with open(self.current_file_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败：{str(e)}")
                return
            # 刷新界面，保持当前章节和滚动位置
            self.reload_current_file()
            self.chapter_listbox.selection_clear(0, tk.END)
            self.chapter_listbox.selection_set(chapter_index)
            self.display_chapter_content(None)
            self.chapter_text.yview_moveto(current_scroll)
            dialog.destroy()
        tk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="存储至当前文件", command=on_save).pack(side=tk.LEFT, padx=5)
        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

    # --------------- 修改调用大模型部分 ---------------
    def modify_selected_text(self):
        # 为了保证能修改文本，先临时设置状态为 normal
        self.chapter_text.config(state=tk.NORMAL)
        entire_text = self.chapter_text.get("1.0", tk.END).strip()
        try:
            selected_text = self.chapter_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected_text = ""
        if not entire_text:
            messagebox.showwarning("提示", "右侧文本框没有内容。")
            return
        if not selected_text.strip():
            messagebox.showwarning("提示", "请先在右侧文本框中选中要修改的内容。")
            return

        # 使用修改方向列表进行选择
        if not self.modification_directions:
            messagebox.showwarning("提示", "当前没有任何修改方向，请先设置修改方向。")
            self.set_modification_direction()
            if not self.modification_directions:
                return

        direction_dialog = tk.Toplevel(self.root)
        direction_dialog.title("选择并编辑修改方向")
        sel_frame = tk.Frame(direction_dialog)
        sel_frame.pack(padx=10, pady=5, fill=tk.X)
        tk.Label(sel_frame, text="请选择修改方向：").pack(side=tk.LEFT)
        selected_direction = tk.StringVar(value=self.modification_directions[0])
        option_menu = tk.OptionMenu(sel_frame, selected_direction, *self.modification_directions, command=lambda v: dir_box.delete("1.0", tk.END) or dir_box.insert("1.0", v))
        option_menu.pack(side=tk.LEFT, padx=5)
        tk.Label(direction_dialog, text="当前修改方向（可编辑，仅本次有效）：").pack(pady=5)
        dir_box = tk.Text(direction_dialog, width=80, height=20, font=("思源黑体", 12))
        dir_box.pack(padx=10, pady=5)
        dir_box.insert("1.0", selected_direction.get())
        def on_next():
            local_mod_dir = dir_box.get("1.0", tk.END).strip()
            direction_dialog.destroy()
            prompt = (
                f"请对我选中的这部分文本进行改写或润色：\n\n"
                f"【修改方向】{local_mod_dir}\n\n"
                f"【待修改文本】\n{selected_text}\n"
            )
            # 创建一个锁定交互的遮罩（仅用于锁定交互，无视觉效果）
            overlay = self.create_overlay()
            def on_complete(result):
                overlay.destroy()  # 解除锁定
                if result is None:
                    return
                self.show_compare_dialog(original_text=selected_text, modified_text=result)
            self.call_api_in_thread(prompt, on_complete)
        tk.Button(direction_dialog, text="下一步", command=on_next).pack(pady=5)
        direction_dialog.transient(self.root)
        direction_dialog.grab_set()
        direction_dialog.wait_window()

    def create_overlay(self):
        """创建一个透明的遮罩层覆盖主窗口，仅锁定交互，不显示视觉遮罩"""
        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        self.root.update_idletasks()
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        overlay.geometry(f"{w}x{h}+{x}+{y}")
        # 设置透明度为0（完全透明），但仍可调用 grab_set 锁定交互
        overlay.attributes("-alpha", 0.0)
        overlay.lift()
        overlay.grab_set()
        return overlay

    def show_compare_dialog(self, original_text, modified_text):
        compare_win = tk.Toplevel(self.root)
        compare_win.title("对比显示（选中内容）")
        try:
            compare_win.state("zoomed")
        except:
            compare_win.geometry("1200x800")
        compare_paned = tk.PanedWindow(compare_win, orient=tk.HORIZONTAL)
        compare_paned.pack(fill=tk.BOTH, expand=True)
        left_frame = tk.Frame(compare_win)
        right_frame = tk.Frame(compare_win)
        compare_paned.add(left_frame, stretch="always")
        compare_paned.add(right_frame, stretch="always")
        scroll_left = tk.Scrollbar(left_frame, orient=tk.VERTICAL)
        scroll_left.pack(side=tk.RIGHT, fill=tk.Y)
        text_orig = tk.Text(left_frame, wrap=tk.WORD, font=("思源黑体", 12),
                             yscrollcommand=scroll_left.set)
        text_orig.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_left.config(command=text_orig.yview)
        scroll_right = tk.Scrollbar(right_frame, orient=tk.VERTICAL)
        scroll_right.pack(side=tk.RIGHT, fill=tk.Y)
        text_mod = tk.Text(right_frame, wrap=tk.WORD, font=("思源黑体", 12),
                            yscrollcommand=scroll_right.set)
        text_mod.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_right.config(command=text_mod.yview)
        text_orig.insert(tk.END, original_text)
        text_mod.insert(tk.END, modified_text)
        bottom_frame = tk.Frame(compare_win)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        orig_len = len(original_text)
        mod_len = len(modified_text)
        info_label = tk.Label(bottom_frame, text=f"原文字数: {orig_len}   |   修改后字数: {mod_len}")
        info_label.pack(side=tk.LEFT, padx=10)
        def save_and_close():
            self.save_modified_selection(original_text, text_mod.get("1.0", tk.END))
            compare_win.destroy()
        save_button = tk.Button(bottom_frame, text="保存修改结果", command=save_and_close)
        save_button.pack(side=tk.RIGHT, padx=10)

    def generate_new_filename(self):
        """
        根据当前加载的原文件名、当前选择的模型名称以及当前时间生成新文件名：
        - 如果原文件名最前方没有序号，则新文件名为 "1-原文件名称-当前选择模型名称→当前时间.txt"。
        - 如果原文件名最前方有序号且包含“思考模型”、“全文模型”或“小说模型”中的任意一个，
          则提取最前方的序号（并加 1）和原文件名称（去掉旧的模型名称和时间部分），
          生成新文件名为 "新序号-原文件名称-当前选择模型名称→当前时间.txt"。
        """
        timestamp = time.strftime("%Y%m%d%H%M%S")
        base_name = os.path.splitext(os.path.basename(self.current_file_path))[0]
        pattern_full = r'^(\d+)-(.+)-(思考模型|全文模型|小说模型)→\d{14}$'
        m = re.match(pattern_full, base_name)
        if m:
            old_serial = int(m.group(1))
            original_name = m.group(2)
            new_serial = old_serial + 1
            new_file_name = f"{new_serial}-{original_name}-{self.current_model_name}→{timestamp}.txt"
        elif re.match(r'^\d+-', base_name) and any(model in base_name for model in ["思考模型", "全文模型", "小说模型"]):
            parts = base_name.split('-', 1)
            try:
                old_serial = int(parts[0])
            except:
                old_serial = 0
            new_serial = old_serial + 1
            remainder = parts[1]
            pattern_trailing = r'(.+)-(思考模型|全文模型|小说模型)→\d{14}$'
            m2 = re.match(pattern_trailing, remainder)
            if m2:
                original_name = m2.group(1)
            else:
                original_name = remainder
            new_file_name = f"{new_serial}-{original_name}-{self.current_model_name}→{timestamp}.txt"
        else:
            new_file_name = f"1-{base_name}-{self.current_model_name}→{timestamp}.txt"
        return new_file_name

    def save_modified_selection(self, original_text, modified_text):
        # 保存大模型修改后的结果：生成新文件，不修改原文件
        if not self.current_file_path:
            messagebox.showwarning("提示", "未记录小说文件名，请先加载小说文件。")
            return
        try:
            with open(self.current_file_path, 'r', encoding='utf-8') as f:
                file_text = f.read()
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败：{str(e)}")
            return

        def remove_leading_spaces(text):
            lines = text.splitlines(True)
            new_lines = []
            for ln in lines:
                new_lines.append(ln[2:] if ln.startswith("　　") else ln)
            return "".join(new_lines)

        clean_original = remove_leading_spaces(original_text).strip('\r\n')
        clean_modified = remove_leading_spaces(modified_text).rstrip('\r\n')

        if not clean_original:
            messagebox.showwarning("提示", "无法识别要替换的原文内容（可能只选了缩进空格）。")
            return

        replaced_block = f"{clean_modified}"
        new_file_text = file_text.replace(clean_original, replaced_block, 1)
        if new_file_text == file_text:
            messagebox.showwarning("提示", "未能在原文件中找到选中的文本，替换失败。")
            return

        # --- 通过选中的原文文字计算当前所在的章节及滚动位置 ---
        chapter_index, scroll_fraction = self.get_chapter_info_from_text(clean_original)
        # ------------------------------------------------------------------------

        dir_name = os.path.dirname(self.current_file_path)
        new_file_name = self.generate_new_filename()
        new_file_path = os.path.join(dir_name, new_file_name)
        try:
            with open(new_file_path, 'w', encoding='utf-8') as f:
                f.write(new_file_text)
            messagebox.showinfo("提示", f"修改内容已保存到文件：\n{new_file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"保存修改内容失败：{str(e)}")
            return

        self.current_file_path = new_file_path
        self.reload_current_file()
        self.chapter_listbox.selection_clear(0, tk.END)
        self.chapter_listbox.selection_set(chapter_index)
        self.display_chapter_content(None)
        self.chapter_text.yview_moveto(scroll_fraction)
        self.file_label.config(text="当前文件: " + os.path.basename(new_file_path))

    def reload_current_file(self):
        if not self.current_file_path:
            return
        try:
            with open(self.current_file_path, 'r', encoding='utf-8') as f:
                novel_text = f.read()
            self.chapters = self.split_into_chapters(novel_text)
        except Exception as e:
            messagebox.showerror("错误", f"重新加载文件失败: {str(e)}")
            return
        self.chapter_listbox.delete(0, tk.END)
        for chap_title in self.chapters.keys():
            self.chapter_listbox.insert(tk.END, chap_title)
        if self.chapter_listbox.size() > 0:
            self.chapter_listbox.selection_clear(0, tk.END)
            self.chapter_listbox.selection_set(0)
            self.display_chapter_content(None)
        self.file_label.config(text="当前文件: " + os.path.basename(self.current_file_path))

    # --------------- 辅助函数：计算章节与滚动位置 ---------------
    def get_scroll_fraction_for_text(self, chapter_content, text_to_match):
        pos = chapter_content.find(text_to_match)
        if pos == -1:
            return 0.0
        lines = chapter_content.splitlines()
        cumulative = 0
        for i, line in enumerate(lines):
            if cumulative + len(line) >= pos:
                return i / max(len(lines), 1)
            cumulative += len(line) + 1  # 加上换行符
        return 0.0

    def get_chapter_info_from_text(self, text_to_match):
        for i, title in enumerate(self.chapter_listbox.get(0, tk.END)):
            chapter_content = self.chapters.get(title, "")
            if text_to_match in chapter_content:
                fraction = self.get_scroll_fraction_for_text(chapter_content, text_to_match)
                return i, fraction
        try:
            chapter_index = self.chapter_listbox.curselection()[0]
        except IndexError:
            chapter_index = 0
        scroll_fraction = self.chapter_text.yview()[0]
        return chapter_index, scroll_fraction

    def get_chapter_info_from_selection(self):
        try:
            selected_text = self.chapter_text.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        except tk.TclError:
            selected_text = ""
        if selected_text:
            return self.get_chapter_info_from_text(selected_text)
        else:
            try:
                chapter_index = self.chapter_listbox.curselection()[0]
            except IndexError:
                chapter_index = 0
            scroll_fraction = self.chapter_text.yview()[0]
            return chapter_index, scroll_fraction

    # --------------- 模型调用相关函数 ---------------
    def config_model(self):
        config_win = tk.Toplevel(self.root)
        config_win.title("配置大模型")
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        new_x = root_x + root_width - 400
        new_y = root_y + root_height - 500
        config_win.geometry(f"+{new_x}+{new_y}")
        notebook = ttk.Notebook(config_win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        entries = {}
        for model_name, cfg in self.model_configs.items():
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=model_name)
            entries[model_name] = {}
            row = 0
            tk.Label(frame, text="API Key:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
            api_key_entry = tk.Entry(frame, width=50)
            api_key_entry.grid(row=row, column=1, padx=5, pady=5)
            api_key_entry.insert(0, cfg.get("api_key", ""))
            entries[model_name]["api_key"] = api_key_entry
            row += 1
            tk.Label(frame, text="URL:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
            url_entry = tk.Entry(frame, width=50)
            url_entry.grid(row=row, column=1, padx=5, pady=5)
            url_entry.insert(0, cfg.get("url", ""))
            entries[model_name]["url"] = url_entry
            row += 1
            tk.Label(frame, text="Model:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
            model_entry = tk.Entry(frame, width=50)
            model_entry.grid(row=row, column=1, padx=5, pady=5)
            model_entry.insert(0, cfg.get("model", ""))
            entries[model_name]["model"] = model_entry
            row += 1
            tk.Label(frame, text="Stream:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
            stream_var = tk.BooleanVar(value=cfg.get("stream", True))
            stream_checkbox = tk.Checkbutton(frame, variable=stream_var)
            stream_checkbox.grid(row=row, column=1, padx=5, pady=5, sticky="w")
            entries[model_name]["stream"] = stream_var
        def save_all_configs():
            for model_name, ctrls in entries.items():
                self.model_configs[model_name]["api_key"] = ctrls["api_key"].get().strip()
                self.model_configs[model_name]["url"] = ctrls["url"].get().strip()
                self.model_configs[model_name]["model"] = ctrls["model"].get().strip()
                self.model_configs[model_name]["stream"] = ctrls["stream"].get()
            self.save_model_configs()
            messagebox.showinfo("提示", "配置已保存！")
            config_win.destroy()
        save_button = tk.Button(config_win, text="保存配置", command=save_all_configs)
        save_button.pack(pady=10)

    def call_api_in_thread(self, prompt, callback):
        def task():
            result = self.call_api(prompt)
            self.root.after(0, lambda: callback(result))
        t = threading.Thread(target=task)
        t.daemon = True
        t.start()

    def call_api(self, prompt):
        config = self.model_configs.get(self.current_model_name, {})
        if not config.get("api_key"):
            self.show_error("请先在【配置模型】中设置 API Key。")
            return None
        payload = {
            "model": config.get("model", ""),
            "messages": [
                {"content": prompt, "role": "user", "name": "用户"}
            ],
            "stream": config.get("stream", True)
        }
        headers = {
            "Authorization": f"Bearer {config.get('api_key')}",
            "Content-Type": "application/json"
        }
        try:
            if config.get("stream", True):
                response = requests.post(config.get("url", ""),
                                         headers=headers,
                                         json=payload,
                                         stream=True,
                                         timeout=60)
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
                                            self.root.after(0, lambda text=chunk_text: self.show_toast(text))
                                except json.JSONDecodeError:
                                    pass
                return all_text
            else:
                response = requests.post(config.get("url", ""),
                                         headers=headers,
                                         json=payload,
                                         timeout=60)
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

    # --------------- Toast 提示（改为弹出单一窗口并刷新窗口内容） ---------------
    def show_toast(self, message, duration=2000):
        # 弹出或更新toast窗口，显示最新消息
        display_message = message
        if self.toast_window is None or not tk.Toplevel.winfo_exists(self.toast_window):
            self.toast_window = tk.Toplevel(self.root)
            self.toast_window.overrideredirect(True)
            # 不抢夺窗口控制
            self.root.update_idletasks()
            root_x = self.root.winfo_x()
            root_y = self.root.winfo_y()
            root_w = self.root.winfo_width()
            root_h = self.root.winfo_height()
            # 固定位置
            self.toast_window.geometry(f"300x100+{root_x + root_w - 320}+{root_y + root_h - 150}")
            self.toast_label = tk.Label(self.toast_window, text=display_message,
                                        font=("思源黑体", 10), bg="black", fg="white", padx=10, pady=5)
            self.toast_label.pack(expand=True, fill=tk.BOTH)
        else:
            # 更新窗口内容
            self.toast_label.config(text=display_message)
        # 重置定时器
        if self.toast_timer is not None:
            self.root.after_cancel(self.toast_timer)
        self.toast_timer = self.root.after(duration, self.close_toast)

    def close_toast(self):
        if self.toast_window is not None:
            self.toast_window.destroy()
        self.toast_window = None
        self.toast_timer = None

    def load_model_configs(self):
        config_path = os.path.join(os.path.dirname(sys.argv[0]), "model_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.model_configs = json.load(f)
            except Exception as e:
                print("读取模型配置文件出错：", e)
        else:
            self.model_configs = {
                "思考模型": {
                    "api_key": "",
                    "url": "https://api.example.com/think",
                    "model": "think-model-01",
                    "stream": False
                },
                "全文模型": {
                    "api_key": "",
                    "url": "https://api.example.com/full",
                    "model": "full-model-01",
                    "stream": True
                },
                "小说模型": {
                    "api_key": "",
                    "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
                    "model": "minimax-text-01",
                    "stream": True
                }
            }

    def save_model_configs(self):
        config_path = os.path.join(os.path.dirname(sys.argv[0]), "model_config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.model_configs, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("保存模型配置文件出错：", e)

if __name__ == "__main__":
    root = tk.Tk()
    app = NovelReader(root)
    try:
        root.state('zoomed')
    except:
        root.geometry("1200x800")
    root.mainloop()
