import os
import sys
import struct
import argparse
from xml.etree import ElementTree as ET

XMP_NS = {
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'Container': 'http://ns.google.com/photos/1.0/container/',
    'Item': 'http://ns.google.com/photos/1.0/container/item/',
    'GCamera': 'http://ns.google.com/photos/1.0/camera/',
}

def find_xmp_data(jpeg_data):
    xmp_start = jpeg_data.find(b'<x:xmpmeta')
    if xmp_start == -1:
        xmp_start = jpeg_data.find(b'http://ns.adobe.com/xap/1.0/')
        if xmp_start != -1:
            xmp_start = jpeg_data.rfind(b'<', 0, xmp_start)
    
    if xmp_start == -1:
        return None
    
    xmp_end = jpeg_data.find(b'</x:xmpmeta>', xmp_start)
    if xmp_end == -1:
        xmp_end = jpeg_data.find(b'</rdf:RDF>', xmp_start)
        if xmp_end != -1:
            xmp_end += len(b'</rdf:RDF>')
    
    if xmp_end == -1:
        return None
    
    return jpeg_data[xmp_start:xmp_end]

def parse_xmp(xmp_data):
    try:
        root = ET.fromstring(xmp_data)
        return root
    except ET.ParseError:
        try:
            xmp_str = xmp_data.decode('utf-8', errors='ignore')
            root = ET.fromstring(xmp_str)
            return root
        except:
            return None

def extract_motion_photo_info(xmp_root):
    info = {
        'is_motion_photo': False,
        'version': None,
        'video_items': [],
        'image_items': [],
        'presentation_timestamp_us': None,
    }
    
    if xmp_root is None:
        return info
    
    for ns in ['GCamera', 'http://ns.google.com/photos/1.0/camera/']:
        try:
            motion_photo_elem = xmp_root.find(f'.//{{{ns}}}MotionPhoto')
            if motion_photo_elem is not None and motion_photo_elem.text and int(motion_photo_elem.text) == 1:
                info['is_motion_photo'] = True
                
                version_elem = xmp_root.find(f'.//{{{ns}}}MotionPhotoVersion')
                if version_elem is not None and version_elem.text:
                    info['version'] = int(version_elem.text)
                
                ts_elem = xmp_root.find(f'.//{{{ns}}}MotionPhotoPresentationTimestampUs')
                if ts_elem is not None and ts_elem.text:
                    info['presentation_timestamp_us'] = int(ts_elem.text)
                break
        except:
            continue
    
    for ns in ['Container', 'http://ns.google.com/photos/1.0/container/']:
        try:
            directory = xmp_root.find(f'.//{{{ns}}}Directory')
            if directory is not None:
                seq = directory.find(f'.//{{{XMP_NS["rdf"]}}}Seq')
                if seq is not None:
                    for li in seq.findall(f'.//{{{XMP_NS["rdf"]}}}li'):
                        for item_ns in ['Item', 'http://ns.google.com/photos/1.0/container/item/']:
                            try:
                                item = li.find(f'.//{{{item_ns}}}Item')
                                if item is not None:
                                    mime_elem = item.find(f'.//{{{item_ns}}}Mime')
                                    semantic_elem = item.find(f'.//{{{item_ns}}}Semantic')
                                    length_elem = item.find(f'.//{{{item_ns}}}Length')
                                    padding_elem = item.find(f'.//{{{item_ns}}}Padding')
                                    
                                    mime = mime_elem.text if mime_elem is not None else ''
                                    semantic = semantic_elem.text if semantic_elem is not None else ''
                                    length = int(length_elem.text) if length_elem is not None and length_elem.text else 0
                                    padding = int(padding_elem.text) if padding_elem is not None and padding_elem.text else 0
                                    
                                    if mime == 'video/mp4' or semantic == 'MotionPhoto':
                                        info['video_items'].append({
                                            'mime': mime,
                                            'semantic': semantic,
                                            'length': length,
                                            'padding': padding,
                                        })
                                    elif mime == 'image/jpeg' or semantic == 'Primary':
                                        info['image_items'].append({
                                            'mime': mime,
                                            'semantic': semantic,
                                            'length': length,
                                            'padding': padding,
                                        })
                                    break
                            except:
                                continue
                break
        except:
            continue
    
    return info

def find_eoi_marker(data):
    eoi_pos = data.rfind(b'\xFF\xD9')
    return eoi_pos

def find_mp4_ftyp_signature(data):
    ftyp_pos = data.find(b'ftyp')
    while ftyp_pos != -1:
        if ftyp_pos >= 4:
            size_bytes = data[ftyp_pos - 4:ftyp_pos]
            try:
                box_size = struct.unpack('>I', size_bytes)[0]
                if box_size >= 8 and box_size <= 1024:
                    return ftyp_pos - 4
            except:
                pass
        ftyp_pos = data.find(b'ftyp', ftyp_pos + 1)
    return -1

def is_valid_mp4_header(data, offset):
    if offset + 8 > len(data):
        return False
    try:
        box_size = struct.unpack('>I', data[offset:offset + 4])[0]
        box_type = data[offset + 4:offset + 8].decode('ascii', errors='ignore')
        return box_type == 'ftyp' and box_size >= 8 and box_size <= len(data) - offset
    except:
        return False

def extract_video_from_motion_photo(input_path, output_path=None, logger=None):
    log = logger if logger else print
    
    try:
        with open(input_path, 'rb') as f:
            data = f.read()
        
        file_size = len(data)
        log(f"文件大小: {file_size} 字节")
        
        xmp_data = find_xmp_data(data)
        if xmp_data is None:
            log("警告: 未找到XMP数据")
            xmp_root = None
        else:
            xmp_root = parse_xmp(xmp_data)
        
        info = extract_motion_photo_info(xmp_root)
        
        if not info['is_motion_photo']:
            log("警告: 未通过XMP元数据检测为动态照片")
        
        if info['version']:
            log(f"动态照片版本: {info['version']}")
        if info['presentation_timestamp_us'] is not None:
            log(f"展示时间戳: {info['presentation_timestamp_us']} 微秒")
        
        video_start = None
        video_length = None
        video_padding = 0
        
        if info['video_items']:
            video_item = info['video_items'][0]
            video_length = video_item['length']
            video_padding = video_item['padding']
            log(f"视频长度(元数据): {video_length} 字节")
            log(f"视频填充(元数据): {video_padding} 字节")
            
            if info['image_items']:
                image_item = info['image_items'][0]
                video_start = image_item['length'] + image_item['padding']
                log(f"视频起始位置(图像项): {video_start} 字节")
        
        if video_start is None:
            eoi_pos = find_eoi_marker(data)
            if eoi_pos != -1:
                video_start = eoi_pos + 2 + video_padding
                log(f"视频起始位置(EOI标记): {video_start} 字节 (EOI在 {eoi_pos})")
            else:
                log("警告: 未找到EOI标记")
        
        if video_length is None:
            ftyp_pos = find_mp4_ftyp_signature(data)
            if ftyp_pos != -1 and video_start is not None:
                if ftyp_pos >= video_start:
                    video_length = file_size - ftyp_pos
                    log(f"视频长度(ftyp位置): {video_length} 字节")
        
        if video_start is None or video_length is None:
            ftyp_pos = find_mp4_ftyp_signature(data)
            if ftyp_pos != -1:
                video_start = ftyp_pos
                video_length = file_size - ftyp_pos
                log(f"使用ftyp签名作为后备: start={video_start}, length={video_length}")
            else:
                log("错误: 无法确定视频位置和长度")
                return False, "无法确定视频位置和长度"
        
        video_end = video_start + video_length
        
        if video_end > file_size:
            log(f"警告: 视频结束位置({video_end})超出文件大小({file_size}), 调整长度")
            video_length = file_size - video_start
            video_end = file_size
        
        if video_start >= file_size:
            log(f"错误: 视频起始位置({video_start})超出文件大小({file_size})")
            return False, "视频起始位置超出文件大小"
        
        video_data = data[video_start:video_end]
        
        if not is_valid_mp4_header(video_data, 0):
            log("警告: 视频数据不包含有效的MP4头部")
            ftyp_pos = find_mp4_ftyp_signature(video_data)
            if ftyp_pos != -1:
                log(f"在提取的数据中找到ftyp, 偏移量 {ftyp_pos}, 正在调整")
                video_data = video_data[ftyp_pos:]
                video_length = len(video_data)
        
        if not is_valid_mp4_header(video_data, 0):
            log("错误: 提取的数据不是有效的MP4文件")
            return False, "提取的数据不是有效的MP4文件"
        
        if output_path is None:
            base_name = os.path.splitext(input_path)[0]
            output_path = base_name + '_video.mp4'
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'wb') as f:
            f.write(video_data)
        
        log(f"视频提取成功: {output_path}")
        log(f"提取的视频大小: {len(video_data)} 字节")
        return True, output_path
    
    except Exception as e:
        log(f"错误: {str(e)}")
        return False, str(e)

def main():
    parser = argparse.ArgumentParser(description='Extract video from Android Motion Photo')
    parser.add_argument('input', help='Input Motion Photo file (JPEG)')
    parser.add_argument('-o', '--output', help='Output video file (MP4)')
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' does not exist")
        sys.exit(1)
    
    success, result = extract_video_from_motion_photo(args.input, args.output)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        main()
    else:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        import threading
        
        class MotionPhotoExtractorApp:
            def __init__(self, root):
                self.root = root
                self.root.title("Motion Photo Extractor")
                self.root.geometry("700x620")
                self.root.resizable(True, True)
                self.root.configure(bg='#f5f5f7')
                
                self.software_dir = os.path.dirname(sys.argv[0]) if hasattr(sys, 'frozen') else os.path.dirname(os.path.abspath(__file__))
                self.output_dir = tk.StringVar(value=self.software_dir)
                self.selected_files = []
                
                self.setup_styles()
                self.setup_ui()
            
            def setup_styles(self):
                style = ttk.Style()
                style.theme_use('clam')
                
                style.configure('Modern.TFrame', background='#f5f5f7')
                style.configure('Card.TFrame', background='white', relief='flat')
                
                style.configure('Title.TLabel', 
                               font=('Segoe UI', 20, 'bold'),
                               background='#f5f5f7',
                               foreground='#1d1d1f')
                
                style.configure('Subtitle.TLabel',
                               font=('Segoe UI', 11),
                               background='#f5f5f7',
                               foreground='#86868b')
                
                style.configure('Label.TLabel',
                               font=('Segoe UI', 10),
                               background='white',
                               foreground='#333333')
                
                style.configure('Modern.TButton',
                               font=('Segoe UI', 10, 'bold'),
                               padding=8,
                               background='#007aff',
                               foreground='white',
                               borderwidth=0)
                style.map('Modern.TButton',
                          background=[('active', '#0066dd'), ('pressed', '#0055cc')],
                          foreground=[('active', 'white'), ('pressed', 'white')])
                
                style.configure('Secondary.TButton',
                               font=('Segoe UI', 10),
                               padding=8,
                               background='#e5e5e5',
                               foreground='#333333',
                               borderwidth=0)
                style.map('Secondary.TButton',
                          background=[('active', '#d5d5d5'), ('pressed', '#c5c5c5')])
                
                style.configure('Modern.TEntry',
                               font=('Segoe UI', 10),
                               padding=6,
                               fieldbackground='white',
                               background='white',
                               bordercolor='#d1d1d6',
                               focuscolor='#007aff')
            
            def create_card(self, parent, padding=(15, 15)):
                card = ttk.Frame(parent, style='Card.TFrame', padding=padding)
                card.pack(fill=tk.X, pady=(0, 12))
                card.configure(relief='solid', borderwidth=1)
                card['borderwidth'] = 1
                card['relief'] = 'solid'
                card.configure(borderwidth=1, relief='solid')
                return card
            
            def setup_ui(self):
                main_frame = ttk.Frame(self.root, style='Modern.TFrame', padding=(20, 20))
                main_frame.pack(fill=tk.BOTH, expand=True)
                
                header_frame = ttk.Frame(main_frame, style='Modern.TFrame')
                header_frame.pack(fill=tk.X, pady=(0, 20))
                
                title_label = ttk.Label(header_frame, text="Motion Photo Extractor", style='Title.TLabel')
                title_label.pack(anchor=tk.W)
                
                subtitle_label = ttk.Label(header_frame, text="提取 Android 动态照片中的视频", style='Subtitle.TLabel')
                subtitle_label.pack(anchor=tk.W, pady=(4, 0))
                
                select_card = self.create_card(main_frame)
                
                button_frame = ttk.Frame(select_card, style='Card.TFrame')
                button_frame.pack(fill=tk.X)
                
                select_btn = ttk.Button(button_frame, text="选择照片文件", command=self.select_files, style='Modern.TButton')
                select_btn.pack(side=tk.LEFT, padx=(0, 10))
                
                clear_btn = ttk.Button(button_frame, text="清空列表", command=self.clear_files, style='Secondary.TButton')
                clear_btn.pack(side=tk.LEFT)
                
                output_card = self.create_card(main_frame)
                
                output_label = ttk.Label(output_card, text="导出目录", style='Label.TLabel')
                output_label.pack(anchor=tk.W, pady=(0, 8))
                
                output_frame = ttk.Frame(output_card, style='Card.TFrame')
                output_frame.pack(fill=tk.X)
                
                output_entry = ttk.Entry(output_frame, textvariable=self.output_dir, width=50, style='Modern.TEntry')
                output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
                
                browse_btn = ttk.Button(output_frame, text="浏览", command=self.browse_output_dir, style='Secondary.TButton')
                browse_btn.pack(side=tk.RIGHT)
                
                files_card = self.create_card(main_frame)
                
                files_header = ttk.Frame(files_card, style='Card.TFrame')
                files_header.pack(fill=tk.X, pady=(0, 10))
                
                files_label = ttk.Label(files_header, text=f"待处理文件 ({len(self.selected_files)})", style='Label.TLabel')
                files_label.pack(anchor=tk.W)
                
                files_count_var = tk.StringVar(value=f"共 {len(self.selected_files)} 个文件")
                files_count_label = ttk.Label(files_header, textvariable=files_count_var, style='Subtitle.TLabel')
                files_count_label.pack(anchor=tk.E)
                
                self.files_count_var = files_count_var
                
                listbox_frame = ttk.Frame(files_card, style='Card.TFrame')
                listbox_frame.pack(fill=tk.BOTH, expand=True)
                
                self.file_listbox = tk.Listbox(listbox_frame, 
                                               selectmode=tk.EXTENDED, 
                                               font=('Segoe UI', 9), 
                                               bg='white', 
                                               fg='#333333',
                                               borderwidth=0,
                                               highlightthickness=0,
                                               selectbackground='#007aff',
                                               selectforeground='white',
                                               height=6)
                self.file_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
                
                scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                self.file_listbox.configure(yscrollcommand=scrollbar.set)
                
                action_card = self.create_card(main_frame)
                
                process_btn = ttk.Button(action_card, text="开始提取视频", command=self.start_processing, style='Modern.TButton')
                process_btn.pack(fill=tk.X)
                
                log_card = self.create_card(main_frame)
                
                log_label = ttk.Label(log_card, text="处理日志", style='Label.TLabel')
                log_label.pack(anchor=tk.W, pady=(0, 10))
                
                log_frame = ttk.Frame(log_card, style='Card.TFrame')
                log_frame.pack(fill=tk.BOTH, expand=True)
                
                self.log_text = tk.Text(log_frame, 
                                        font=('Consolas', 9), 
                                        bg='#1d1d1f', 
                                        fg='#e5e5e5',
                                        borderwidth=0,
                                        highlightthickness=0,
                                        state=tk.DISABLED,
                                        height=8,
                                        insertbackground='white')
                self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
                
                log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
                log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                self.log_text.configure(yscrollcommand=log_scrollbar.set)
            
            def select_files(self):
                files = filedialog.askopenfilenames(
                    title="选择动态照片文件",
                    filetypes=[("JPEG图片", "*.jpg *.jpeg"), ("所有文件", "*.*")]
                )
                if files:
                    for file in files:
                        if file not in self.selected_files:
                            self.selected_files.append(file)
                            self.file_listbox.insert(tk.END, os.path.basename(file))
                    self.files_count_var.set(f"共 {len(self.selected_files)} 个文件")
            
            def clear_files(self):
                self.selected_files = []
                self.file_listbox.delete(0, tk.END)
                self.files_count_var.set(f"共 {len(self.selected_files)} 个文件")
            
            def browse_output_dir(self):
                directory = filedialog.askdirectory(title="选择导出目录", initialdir=self.output_dir.get())
                if directory:
                    self.output_dir.set(directory)
            
            def log(self, message):
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, message + '\n')
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
                self.root.update_idletasks()
            
            def start_processing(self):
                if not self.selected_files:
                    messagebox.showwarning("警告", "请先选择要处理的文件")
                    return
                
                output_dir = self.output_dir.get()
                if not os.path.isdir(output_dir):
                    try:
                        os.makedirs(output_dir)
                    except:
                        messagebox.showerror("错误", "无法创建导出目录")
                        return
                
                self.log(f"开始处理 {len(self.selected_files)} 个文件...")
                self.log(f"导出目录: {output_dir}")
                
                thread = threading.Thread(target=self.process_files, args=(output_dir,))
                thread.start()
            
            def process_files(self, output_dir):
                success_count = 0
                fail_count = 0
                
                for i, input_path in enumerate(self.selected_files, 1):
                    self.log(f"\n--- 处理文件 {i}/{len(self.selected_files)} ---")
                    self.log(f"文件: {os.path.basename(input_path)}")
                    
                    base_name = os.path.splitext(os.path.basename(input_path))[0]
                    output_path = os.path.join(output_dir, base_name + '_video.mp4')
                    
                    success, result = extract_video_from_motion_photo(input_path, output_path, self.log)
                    
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                
                self.log(f"\n=== 处理完成 ===")
                self.log(f"成功: {success_count} 个")
                self.log(f"失败: {fail_count} 个")
                
                if success_count > 0:
                    messagebox.showinfo("完成", f"提取完成！\n成功: {success_count} 个\n失败: {fail_count} 个")
        
        root = tk.Tk()
        app = MotionPhotoExtractorApp(root)
        root.mainloop()