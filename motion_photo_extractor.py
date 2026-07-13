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
    'MiCamera': 'http://ns.miui.com/photos/1.0/camera/',
    'MiContainer': 'http://ns.miui.com/photos/1.0/container/',
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

def parse_exif(jpeg_data):
    exif_info = {}
    
    app1_marker = b'\xFF\xE1'
    offset = 0
    
    while True:
        marker_pos = jpeg_data.find(app1_marker, offset)
        if marker_pos == -1:
            break
        
        if marker_pos + 4 > len(jpeg_data):
            break
        
        segment_length = struct.unpack('>H', jpeg_data[marker_pos + 2:marker_pos + 4])[0]
        
        if marker_pos + 4 + segment_length > len(jpeg_data):
            break
        
        segment_data = jpeg_data[marker_pos + 4:marker_pos + 4 + segment_length]
        
        if segment_data.startswith(b'Exif\x00\x00'):
            exif_data = segment_data[6:]
            if len(exif_data) >= 8:
                byte_order = exif_data[0:2]
                if byte_order == b'II':
                    fmt = '<'
                elif byte_order == b'MM':
                    fmt = '>'
                else:
                    offset = marker_pos + 4 + segment_length
                    continue
                
                magic = struct.unpack(f'{fmt}H', exif_data[2:4])[0]
                if magic != 0x002A:
                    offset = marker_pos + 4 + segment_length
                    continue
                
                first_ifd_offset = struct.unpack(f'{fmt}I', exif_data[4:8])[0]
                
                exif_info = parse_tiff_ifd(exif_data, fmt, first_ifd_offset)
            
            break
        
        offset = marker_pos + 4 + segment_length
    
    return exif_info

def parse_tiff_ifd(data, fmt, ifd_offset):
    info = {}
    
    exif_tags = {
        0x0100: ('ImageWidth', 'int'),
        0x0101: ('ImageHeight', 'int'),
        0x0102: ('BitsPerSample', 'int'),
        0x0103: ('Compression', 'int'),
        0x0106: ('PhotometricInterpretation', 'int'),
        0x0112: ('Orientation', 'int'),
        0x0115: ('SamplesPerPixel', 'int'),
        0x011A: ('XResolution', 'rational'),
        0x011B: ('YResolution', 'rational'),
        0x0128: ('ResolutionUnit', 'int'),
        0x0131: ('Software', 'string'),
        0x0132: ('DateTime', 'string'),
        0x013B: ('Artist', 'string'),
        0x0211: ('YCbCrPositioning', 'int'),
        0x0213: ('StripOffsets', 'int'),
        0x0216: ('RowsPerStrip', 'int'),
        0x0217: ('StripByteCounts', 'int'),
        0x021A: ('XResolution', 'rational'),
        0x021D: ('TransferFunction', 'int'),
        0x0221: ('YCbCrCoefficients', 'rational'),
        0x0222: ('YCbCrSubSampling', 'int'),
        0x0223: ('YCbCrPositioning', 'int'),
        0x0227: ('ReferenceBlackWhite', 'rational'),
        0x0231: ('Copyright', 'string'),
        0x8298: ('Copyright', 'string'),
        0x829A: ('ExposureTime', 'rational'),
        0x829D: ('FNumber', 'rational'),
        0x8769: ('ExifOffset', 'int'),
        0x8773: ('InteroperabilityOffset', 'int'),
        0x9000: ('ExifVersion', 'string'),
        0x9003: ('DateTimeOriginal', 'string'),
        0x9004: ('DateTimeDigitized', 'string'),
        0x9101: ('ComponentsConfiguration', 'string'),
        0x9102: ('CompressedBitsPerPixel', 'rational'),
        0x9201: ('ShutterSpeedValue', 'rational'),
        0x9202: ('ApertureValue', 'rational'),
        0x9203: ('BrightnessValue', 'rational'),
        0x9204: ('ExposureBiasValue', 'rational'),
        0x9205: ('MaxApertureValue', 'rational'),
        0x9206: ('SubjectDistance', 'rational'),
        0x9207: ('MeteringMode', 'int'),
        0x9208: ('LightSource', 'int'),
        0x9209: ('Flash', 'int'),
        0x920A: ('FocalLength', 'rational'),
        0x9214: ('SubjectArea', 'int'),
        0x927C: ('MakerNote', 'string'),
        0x9286: ('UserComment', 'string'),
        0x9320: ('FlashpixVersion', 'string'),
        0xA000: ('FlashpixVersion', 'string'),
        0xA001: ('ColorSpace', 'int'),
        0xA002: ('ExifImageWidth', 'int'),
        0xA003: ('ExifImageHeight', 'int'),
        0xA004: ('RelatedSoundFile', 'string'),
        0xA005: ('InteroperabilityOffset', 'int'),
        0xA20B: ('FlashEnergy', 'rational'),
        0xA20C: ('SpatialFrequencyResponse', 'string'),
        0xA20E: ('FocalPlaneXResolution', 'rational'),
        0xA20F: ('FocalPlaneYResolution', 'rational'),
        0xA210: ('FocalPlaneResolutionUnit', 'int'),
        0xA214: ('SubjectLocation', 'int'),
        0xA215: ('ExposureIndex', 'rational'),
        0xA217: ('SensingMethod', 'int'),
        0xA300: ('FileSource', 'string'),
        0xA301: ('SceneType', 'string'),
        0xA302: ('CFAPattern', 'string'),
        0xA401: ('CustomRendered', 'int'),
        0xA402: ('ExposureMode', 'int'),
        0xA403: ('WhiteBalance', 'int'),
        0xA404: ('DigitalZoomRatio', 'rational'),
        0xA405: ('FocalLengthIn35mmFilm', 'int'),
        0xA406: ('SceneCaptureType', 'int'),
        0xA407: ('GainControl', 'int'),
        0xA408: ('Contrast', 'int'),
        0xA409: ('Saturation', 'int'),
        0xA40A: ('Sharpness', 'int'),
        0xA40B: ('DeviceSettingDescription', 'string'),
        0xA40C: ('SubjectDistanceRange', 'int'),
        0xA420: ('ImageUniqueID', 'string'),
        0x010F: ('Make', 'string'),
        0x0110: ('Model', 'string'),
        0x0111: ('StripOffsets', 'int'),
        0x8298: ('Copyright', 'string'),
        0x0000: ('GPSVersionID', 'string'),
        0x0001: ('GPSLatitudeRef', 'string'),
        0x0002: ('GPSLatitude', 'rational'),
        0x0003: ('GPSLongitudeRef', 'string'),
        0x0004: ('GPSLongitude', 'rational'),
        0x0005: ('GPSAltitudeRef', 'int'),
        0x0006: ('GPSAltitude', 'rational'),
        0x0007: ('GPSTimeStamp', 'rational'),
        0x0008: ('GPSSatellites', 'string'),
        0x0009: ('GPSStatus', 'string'),
        0x000A: ('GPSMeasureMode', 'string'),
        0x000B: ('GPSDOP', 'rational'),
        0x000C: ('GPSSpeedRef', 'string'),
        0x000D: ('GPSSpeed', 'rational'),
        0x000E: ('GPSTrackRef', 'string'),
        0x000F: ('GPSTrack', 'rational'),
        0x0010: ('GPSImgDirectionRef', 'string'),
        0x0011: ('GPSImgDirection', 'rational'),
        0x0012: ('GPSMapDatum', 'string'),
        0x0013: ('GPSDestLatitudeRef', 'string'),
        0x0014: ('GPSDestLatitude', 'rational'),
        0x0015: ('GPSDestLongitudeRef', 'string'),
        0x0016: ('GPSDestLongitude', 'rational'),
        0x0017: ('GPSDestBearingRef', 'string'),
        0x0018: ('GPSDestBearing', 'rational'),
        0x0019: ('GPSDestDistanceRef', 'string'),
        0x001A: ('GPSDestDistance', 'rational'),
        0x001B: ('GPSProcessingMethod', 'string'),
        0x001C: ('GPSAreaInformation', 'string'),
        0x001D: ('GPSDateStamp', 'string'),
        0x001E: ('GPSDifferential', 'int'),
    }
    
    try:
        num_entries = struct.unpack(f'{fmt}H', data[ifd_offset:ifd_offset + 2])[0]
        
        for i in range(num_entries):
            entry_offset = ifd_offset + 2 + i * 12
            
            if entry_offset + 12 > len(data):
                break
            
            tag_id = struct.unpack(f'{fmt}H', data[entry_offset:entry_offset + 2])[0]
            tag_type = struct.unpack(f'{fmt}H', data[entry_offset + 2:entry_offset + 4])[0]
            num_values = struct.unpack(f'{fmt}I', data[entry_offset + 4:entry_offset + 8])[0]
            value_offset = struct.unpack(f'{fmt}I', data[entry_offset + 8:entry_offset + 12])[0]
            
            if tag_id in exif_tags:
                tag_name, tag_format = exif_tags[tag_id]
                
                if tag_name in info:
                    continue
                
                try:
                    if tag_type == 2:
                        if value_offset + num_values > len(data):
                            continue
                        str_data = data[value_offset:value_offset + num_values]
                        info[tag_name] = str_data.decode('utf-8', errors='ignore').rstrip('\x00')
                    elif tag_type == 3:
                        if value_offset + 2 * num_values > len(data):
                            continue
                        info[tag_name] = struct.unpack(f'{fmt}H', data[value_offset:value_offset + 2])[0]
                    elif tag_type == 4:
                        if value_offset + 4 * num_values > len(data):
                            continue
                        info[tag_name] = struct.unpack(f'{fmt}I', data[value_offset:value_offset + 4])[0]
                    elif tag_type == 5:
                        if value_offset + 8 * num_values > len(data):
                            continue
                        numerator = struct.unpack(f'{fmt}I', data[value_offset:value_offset + 4])[0]
                        denominator = struct.unpack(f'{fmt}I', data[value_offset + 4:value_offset + 8])[0]
                        if denominator != 0:
                            info[tag_name] = numerator / denominator
                        else:
                            info[tag_name] = numerator
                    elif tag_type == 1:
                        if value_offset + num_values > len(data):
                            continue
                        info[tag_name] = data[value_offset]
                    else:
                        pass
                except:
                    pass
        
        next_ifd_offset = struct.unpack(f'{fmt}I', data[ifd_offset + 2 + num_entries * 12:ifd_offset + 2 + num_entries * 12 + 4])[0]
        
        if next_ifd_offset != 0 and next_ifd_offset < len(data):
            sub_info = parse_tiff_ifd(data, fmt, next_ifd_offset)
            info.update(sub_info)
    
    except:
        pass
    
    return info

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
        'xmp_debug': '',
    }
    
    if xmp_root is None:
        return info
    
    ns_list = [
        'GCamera', 
        'http://ns.google.com/photos/1.0/camera/',
        'MiCamera',
        'http://ns.miui.com/photos/1.0/camera/',
        'http://ns.mi.com/camera/',
        'http://xiaomi.com/camera/',
    ]
    
    for ns in ns_list:
        try:
            motion_photo_elem = xmp_root.find(f'.//{{{ns}}}MotionPhoto')
            if motion_photo_elem is not None and motion_photo_elem.text and int(motion_photo_elem.text) == 1:
                info['is_motion_photo'] = True
                info['xmp_debug'] = f"检测到动态照片标记 (命名空间: {ns})"
                
                version_elem = xmp_root.find(f'.//{{{ns}}}MotionPhotoVersion')
                if version_elem is not None and version_elem.text:
                    info['version'] = int(version_elem.text)
                
                ts_elem = xmp_root.find(f'.//{{{ns}}}MotionPhotoPresentationTimestampUs')
                if ts_elem is not None and ts_elem.text:
                    info['presentation_timestamp_us'] = int(ts_elem.text)
                break
        except:
            continue
    
    if not info['is_motion_photo']:
        for ns in ns_list:
            try:
                motion_photo_elem = xmp_root.find(f'.//{{{ns}}}MotionPhoto')
                if motion_photo_elem is not None:
                    info['xmp_debug'] = f"找到MotionPhoto标记但值为: {motion_photo_elem.text} (命名空间: {ns})"
                    break
            except:
                continue
    
    container_ns_list = [
        'Container', 
        'http://ns.google.com/photos/1.0/container/',
        'MiContainer',
        'http://ns.miui.com/photos/1.0/container/',
        'http://ns.mi.com/container/',
        'http://xiaomi.com/container/',
    ]
    
    for ns in container_ns_list:
        try:
            directory = xmp_root.find(f'.//{{{ns}}}Directory')
            if directory is not None:
                seq = directory.find(f'.//{{{XMP_NS["rdf"]}}}Seq')
                if seq is not None:
                    for li in seq.findall(f'.//{{{XMP_NS["rdf"]}}}li'):
                        item_ns_list = [
                            'Item', 
                            'http://ns.google.com/photos/1.0/container/item/',
                            'http://ns.miui.com/photos/1.0/container/item/',
                            'http://ns.mi.com/container/item/',
                        ]
                        for item_ns in item_ns_list:
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
                                    
                                    video_semantics = ['MotionPhoto', 'motion_photo', 'video', 'Video', 'MV']
                                    image_semantics = ['Primary', 'primary', 'image', 'Image', 'MAIN']
                                    
                                    if mime == 'video/mp4' or semantic in video_semantics:
                                        info['video_items'].append({
                                            'mime': mime,
                                            'semantic': semantic,
                                            'length': length,
                                            'padding': padding,
                                        })
                                    elif mime == 'image/jpeg' or semantic in image_semantics:
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
    
    if not info['video_items'] and not info['image_items']:
        all_elements = []
        for elem in xmp_root.iter():
            tag = elem.tag
            if '}' in tag:
                tag = tag.split('}')[1]
            all_elements.append(tag)
        
        unique_tags = list(set(all_elements))
        info['xmp_debug'] = f"未找到标准Container结构，XMP中包含的标签: {', '.join(unique_tags[:20])}"
    
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

def parse_motion_photo_metadata(input_path):
    metadata = {
        'file_path': input_path,
        'file_name': os.path.basename(input_path),
        'file_size': 0,
        'is_motion_photo': False,
        'has_xmp': False,
        'xmp_size': 0,
        'xmp_raw': '',
        'version': None,
        'presentation_timestamp_us': None,
        'presentation_timestamp_ms': None,
        'video_items': [],
        'image_items': [],
        'video_start': None,
        'video_length': None,
        'video_end': None,
        'video_padding': 0,
        'eoi_position': None,
        'ftyp_position': None,
        'detected_method': None,
        'is_valid_mp4': False,
        'video_duration_estimate': None,
        'xmp_debug': '',
        'detected_as_motion': False,
        'exif': {},
    }
    
    try:
        with open(input_path, 'rb') as f:
            data = f.read()
        
        metadata['file_size'] = len(data)
        
        metadata['exif'] = parse_exif(data)
        
        xmp_data = find_xmp_data(data)
        if xmp_data is not None:
            metadata['has_xmp'] = True
            metadata['xmp_size'] = len(xmp_data)
            metadata['xmp_raw'] = xmp_data.decode('utf-8', errors='ignore')[:3000]
            
            xmp_root = parse_xmp(xmp_data)
            info = extract_motion_photo_info(xmp_root)
            
            metadata['is_motion_photo'] = info['is_motion_photo']
            metadata['version'] = info['version']
            metadata['presentation_timestamp_us'] = info['presentation_timestamp_us']
            metadata['xmp_debug'] = info.get('xmp_debug', '')
            
            if info['presentation_timestamp_us'] is not None:
                metadata['presentation_timestamp_ms'] = info['presentation_timestamp_us'] // 1000
            
            metadata['video_items'] = info['video_items']
            metadata['image_items'] = info['image_items']
        
        eoi_pos = find_eoi_marker(data)
        metadata['eoi_position'] = eoi_pos
        
        ftyp_pos = find_mp4_ftyp_signature(data)
        metadata['ftyp_position'] = ftyp_pos
        
        if ftyp_pos != -1 and eoi_pos != -1 and ftyp_pos > eoi_pos:
            metadata['detected_as_motion'] = True
            if not metadata['is_motion_photo']:
                if not metadata['xmp_debug']:
                    metadata['xmp_debug'] = f"通过文件结构检测为动态照片 (EOI: {eoi_pos}, ftyp: {ftyp_pos})"
        
        video_start = None
        video_length = None
        video_padding = 0
        
        if metadata['video_items']:
            video_item = metadata['video_items'][0]
            video_length = video_item['length']
            video_padding = video_item['padding']
            
            if metadata['image_items']:
                image_item = metadata['image_items'][0]
                video_start = image_item['length'] + image_item['padding']
                metadata['detected_method'] = 'Container Directory (XMP)'
        
        if video_start is None and eoi_pos != -1:
            video_start = eoi_pos + 2 + video_padding
            metadata['detected_method'] = 'EOI Marker'
        
        if video_length is None and ftyp_pos != -1 and video_start is not None:
            if ftyp_pos >= video_start:
                video_length = metadata['file_size'] - ftyp_pos
        
        if video_start is None or video_length is None:
            if ftyp_pos != -1:
                video_start = ftyp_pos
                video_length = metadata['file_size'] - ftyp_pos
                metadata['detected_method'] = 'MP4 ftyp Signature'
        
        metadata['video_start'] = video_start
        metadata['video_length'] = video_length
        metadata['video_padding'] = video_padding
        
        if video_start is not None and video_length is not None:
            video_end = video_start + video_length
            if video_end > metadata['file_size']:
                video_length = metadata['file_size'] - video_start
                video_end = metadata['file_size']
            metadata['video_end'] = video_end
            
            if video_start < metadata['file_size']:
                video_data = data[video_start:video_end]
                if is_valid_mp4_header(video_data, 0):
                    metadata['is_valid_mp4'] = True
                else:
                    ftyp_pos_in_video = find_mp4_ftyp_signature(video_data)
                    if ftyp_pos_in_video != -1:
                        video_data = video_data[ftyp_pos_in_video:]
                        if is_valid_mp4_header(video_data, 0):
                            metadata['is_valid_mp4'] = True
        
        if metadata['is_valid_mp4'] and metadata['video_length']:
            avg_bitrate_kbps = 5000
            duration_seconds = (metadata['video_length'] * 8) / (avg_bitrate_kbps * 1000)
            metadata['video_duration_estimate'] = f"{duration_seconds:.2f} 秒"
    
    except Exception as e:
        metadata['error'] = str(e)
    
    return metadata

def extract_video_from_motion_photo(input_path, output_path=None, logger=None):
    log = logger if logger else print
    
    try:
        metadata = parse_motion_photo_metadata(input_path)
        
        log(f"文件大小: {metadata['file_size']} 字节")
        
        if not metadata['has_xmp']:
            log("警告: 未找到XMP数据")
        
        if not metadata['is_motion_photo']:
            log("警告: 未通过XMP元数据检测为动态照片")
        
        if metadata['version']:
            log(f"动态照片版本: {metadata['version']}")
        if metadata['presentation_timestamp_us'] is not None:
            log(f"展示时间戳: {metadata['presentation_timestamp_us']} 微秒")
        
        if metadata['video_items']:
            video_item = metadata['video_items'][0]
            log(f"视频长度(元数据): {video_item['length']} 字节")
            log(f"视频填充(元数据): {video_item['padding']} 字节")
        
        if metadata['image_items']:
            image_item = metadata['image_items'][0]
            log(f"图像长度(元数据): {image_item['length']} 字节")
            log(f"图像填充(元数据): {image_item['padding']} 字节")
        
        log(f"视频起始位置: {metadata['video_start']} 字节")
        log(f"视频长度: {metadata['video_length']} 字节")
        log(f"检测方法: {metadata['detected_method']}")
        
        if metadata['video_start'] is None or metadata['video_length'] is None:
            log("错误: 无法确定视频位置和长度")
            return False, "无法确定视频位置和长度"
        
        with open(input_path, 'rb') as f:
            data = f.read()
        
        video_data = data[metadata['video_start']:metadata['video_end']]
        
        if not is_valid_mp4_header(video_data, 0):
            log("警告: 视频数据不包含有效的MP4头部")
            ftyp_pos = find_mp4_ftyp_signature(video_data)
            if ftyp_pos != -1:
                log(f"在提取的数据中找到ftyp, 偏移量 {ftyp_pos}, 正在调整")
                video_data = video_data[ftyp_pos:]
        
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
                
                files_action_frame = ttk.Frame(files_card, style='Card.TFrame')
                files_action_frame.pack(fill=tk.X, pady=(10, 0))
                
                detail_btn = ttk.Button(files_action_frame, text="查看详情", command=self.show_details, style='Secondary.TButton')
                detail_btn.pack(side=tk.RIGHT)
                
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
            
            def show_details(self):
                selected_indices = self.file_listbox.curselection()
                if not selected_indices:
                    messagebox.showwarning("提示", "请先选择一个文件")
                    return
                
                selected_index = selected_indices[0]
                if selected_index < len(self.selected_files):
                    file_path = self.selected_files[selected_index]
                    DetailWindow(self.root, file_path)
            
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
        
        class DetailWindow:
            def __init__(self, parent, file_path):
                self.parent = parent
                self.file_path = file_path
                
                self.window = tk.Toplevel(parent)
                self.window.title(f"动态照片详情 - {os.path.basename(file_path)}")
                self.window.geometry("600x800")
                self.window.configure(bg='#f5f5f7')
                self.window.resizable(True, True)
                self.window.transient(parent)
                self.window.grab_set()
                
                self.setup_ui()
            
            def setup_ui(self):
                canvas = tk.Canvas(self.window, bg='#f5f5f7', highlightthickness=0)
                scrollbar = ttk.Scrollbar(self.window, orient=tk.VERTICAL, command=canvas.yview)
                main_frame = ttk.Frame(canvas, style='Modern.TFrame', padding=(20, 20))
                
                main_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
                canvas.create_window((0, 0), window=main_frame, anchor="nw")
                canvas.configure(yscrollcommand=scrollbar.set)
                
                canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                
                canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
                
                title_label = ttk.Label(main_frame, text="动态照片详细信息", style='Title.TLabel')
                title_label.pack(anchor=tk.W, pady=(0, 15))
                
                metadata = parse_motion_photo_metadata(self.file_path)
                
                file_card = self.create_card(main_frame, "文件信息")
                self.add_info_row(file_card, "文件名", metadata['file_name'])
                self.add_info_row(file_card, "文件路径", metadata['file_path'])
                self.add_info_row(file_card, "文件大小", self.format_size(metadata['file_size']))
                
                status_card = self.create_card(main_frame, "状态检测")
                
                is_motion = metadata['is_motion_photo'] or metadata.get('detected_as_motion', False)
                status_color = '#34c759' if is_motion else '#ff3b30'
                status_text = '是' if is_motion else '否'
                self.add_info_row(status_card, "是否动态照片", status_text, status_color)
                
                if metadata.get('detected_as_motion', False) and not metadata['is_motion_photo']:
                    self.add_info_row(status_card, "检测方式", "文件结构检测", '#ff9500')
                
                xmp_color = '#34c759' if metadata['has_xmp'] else '#ff3b30'
                xmp_text = '是' if metadata['has_xmp'] else '否'
                self.add_info_row(status_card, "包含XMP元数据", xmp_text, xmp_color)
                
                if metadata['has_xmp']:
                    self.add_info_row(status_card, "XMP数据大小", self.format_size(metadata['xmp_size']))
                
                mp4_color = '#34c759' if metadata['is_valid_mp4'] else '#ff3b30'
                mp4_text = '是' if metadata['is_valid_mp4'] else '否'
                self.add_info_row(status_card, "视频格式有效", mp4_text, mp4_color)
                
                version_card = self.create_card(main_frame, "版本信息")
                self.add_info_row(version_card, "动态照片版本", metadata['version'] if metadata['version'] else '未知')
                self.add_info_row(version_card, "展示时间戳", 
                                f"{metadata['presentation_timestamp_us']} 微秒" if metadata['presentation_timestamp_us'] else '未知')
                if metadata['presentation_timestamp_ms']:
                    self.add_info_row(version_card, "展示时间戳(毫秒)", f"{metadata['presentation_timestamp_ms']} ms")
                
                container_card = self.create_card(main_frame, "容器目录")
                if metadata['image_items']:
                    for i, item in enumerate(metadata['image_items'], 1):
                        self.add_info_row(container_card, f"图像项 {i} - MIME", item.get('mime', ''))
                        self.add_info_row(container_card, f"图像项 {i} - 语义", item.get('semantic', ''))
                        self.add_info_row(container_card, f"图像项 {i} - 长度", self.format_size(item.get('length', 0)))
                        self.add_info_row(container_card, f"图像项 {i} - 填充", self.format_size(item.get('padding', 0)))
                else:
                    self.add_info_row(container_card, "图像项", "无")
                
                if metadata['video_items']:
                    for i, item in enumerate(metadata['video_items'], 1):
                        self.add_info_row(container_card, f"视频项 {i} - MIME", item.get('mime', ''))
                        self.add_info_row(container_card, f"视频项 {i} - 语义", item.get('semantic', ''))
                        self.add_info_row(container_card, f"视频项 {i} - 长度", self.format_size(item.get('length', 0)))
                        self.add_info_row(container_card, f"视频项 {i} - 填充", self.format_size(item.get('padding', 0)))
                else:
                    self.add_info_row(container_card, "视频项", "无")
                
                position_card = self.create_card(main_frame, "位置信息")
                self.add_info_row(position_card, "视频起始位置", f"{metadata['video_start']} 字节" if metadata['video_start'] is not None else '未知')
                self.add_info_row(position_card, "视频长度", f"{metadata['video_length']} 字节" if metadata['video_length'] is not None else '未知')
                self.add_info_row(position_card, "视频结束位置", f"{metadata['video_end']} 字节" if metadata['video_end'] is not None else '未知')
                self.add_info_row(position_card, "视频填充", f"{metadata['video_padding']} 字节")
                self.add_info_row(position_card, "EOI标记位置", f"{metadata['eoi_position']} 字节" if metadata['eoi_position'] is not None else '未找到')
                self.add_info_row(position_card, "ftyp签名位置", f"{metadata['ftyp_position']} 字节" if metadata['ftyp_position'] is not None else '未找到')
                self.add_info_row(position_card, "检测方法", metadata['detected_method'] if metadata['detected_method'] else '未知')
                
                estimate_card = self.create_card(main_frame, "预估信息")
                self.add_info_row(estimate_card, "视频时长(估算)", metadata['video_duration_estimate'] if metadata['video_duration_estimate'] else '未知')
                
                exif = metadata.get('exif', {})
                if exif:
                    exif_card = self.create_card(main_frame, "照片参数 (EXIF)")
                    
                    exif_fields = [
                        ('Make', '设备品牌'),
                        ('Model', '设备型号'),
                        ('DateTime', '拍摄时间'),
                        ('DateTimeOriginal', '原始时间'),
                        ('DateTimeDigitized', '数字化时间'),
                        ('ImageWidth', '图像宽度'),
                        ('ImageHeight', '图像高度'),
                        ('ExifImageWidth', '实际宽度'),
                        ('ExifImageHeight', '实际高度'),
                        ('Orientation', '方向'),
                        ('ExposureTime', '曝光时间'),
                        ('FNumber', '光圈值'),
                        ('FocalLength', '焦距'),
                        ('FocalLengthIn35mmFilm', '等效焦距(35mm)'),
                        ('ISO', 'ISO感光度'),
                        ('ISO', 'ISO'),
                        ('ShutterSpeedValue', '快门速度'),
                        ('ApertureValue', '光圈值'),
                        ('BrightnessValue', '亮度'),
                        ('ExposureBiasValue', '曝光补偿'),
                        ('MaxApertureValue', '最大光圈'),
                        ('MeteringMode', '测光模式'),
                        ('Flash', '闪光灯'),
                        ('WhiteBalance', '白平衡'),
                        ('ExposureMode', '曝光模式'),
                        ('Saturation', '饱和度'),
                        ('Contrast', '对比度'),
                        ('Sharpness', '锐度'),
                        ('DigitalZoomRatio', '数码变焦'),
                        ('Software', '拍摄软件'),
                        ('GPSLatitude', 'GPS纬度'),
                        ('GPSLongitude', 'GPS经度'),
                        ('GPSAltitude', 'GPS海拔'),
                    ]
                    
                    for field_name, display_name in exif_fields:
                        if field_name in exif:
                            value = exif[field_name]
                            if isinstance(value, float):
                                if field_name in ['ExposureTime', 'ShutterSpeedValue']:
                                    value_str = f"{value:.4f} s"
                                elif field_name in ['FNumber', 'ApertureValue', 'MaxApertureValue']:
                                    value_str = f"f/{value:.1f}"
                                elif field_name in ['FocalLength', 'FocalLengthIn35mmFilm']:
                                    value_str = f"{value:.1f} mm"
                                elif field_name in ['BrightnessValue', 'ExposureBiasValue']:
                                    value_str = f"{value:.1f} EV"
                                else:
                                    value_str = f"{value:.2f}"
                            elif isinstance(value, int):
                                if field_name == 'Orientation':
                                    orient_map = {1: '正常', 2: '水平翻转', 3: '旋转180°', 4: '垂直翻转', 
                                                  5: '顺时针90°+水平翻转', 6: '顺时针90°', 
                                                  7: '逆时针90°+水平翻转', 8: '逆时针90°'}
                                    value_str = orient_map.get(value, str(value))
                                elif field_name == 'Flash':
                                    flash_on = (value & 0x01) == 1
                                    flash_return = (value & 0x06) >> 1
                                    flash_map = {0: '无返回', 1: '返回检测到', 2: '返回未检测到', 3: '未定义'}
                                    value_str = f"{'开启' if flash_on else '关闭'} ({flash_map.get(flash_return, '')})"
                                elif field_name == 'MeteringMode':
                                    meter_map = {0: '未知', 1: '平均', 2: '中央重点', 3: '点测光', 
                                                 4: '多点', 5: '多区域', 6: '部分', 255: '其他'}
                                    value_str = meter_map.get(value, str(value))
                                elif field_name == 'ExposureMode':
                                    exp_map = {0: '自动', 1: '手动', 2: '自动包围'}
                                    value_str = exp_map.get(value, str(value))
                                elif field_name == 'WhiteBalance':
                                    wb_map = {0: '自动', 1: '手动'}
                                    value_str = wb_map.get(value, str(value))
                                elif field_name in ['Contrast', 'Saturation', 'Sharpness', 'GainControl']:
                                    setting_map = {0: '标准', 1: '低', 2: '高'}
                                    value_str = setting_map.get(value, str(value))
                                else:
                                    value_str = str(value)
                            else:
                                value_str = str(value)
                            
                            self.add_info_row(exif_card, display_name, value_str)
                
                if metadata.get('xmp_raw', ''):
                    xmp_card = self.create_card(main_frame, "原始XMP数据")
                    xmp_text = tk.Text(xmp_card, height=8, font=('Consolas', 8), wrap=tk.WORD, 
                                      bg='#f5f5f7', fg='#333333', borderwidth=0)
                    xmp_text.insert(tk.END, metadata['xmp_raw'])
                    xmp_text.config(state=tk.DISABLED)
                    xmp_text.pack(fill=tk.X)
                
                if metadata.get('xmp_debug', ''):
                    debug_card = self.create_card(main_frame, "检测详情")
                    self.add_info_row(debug_card, "详情", metadata['xmp_debug'], '#007aff')
                
                if 'error' in metadata:
                    error_card = self.create_card(main_frame, "错误信息")
                    self.add_info_row(error_card, "错误", metadata['error'], '#ff3b30')
                
                close_btn = ttk.Button(main_frame, text="关闭", command=self.window.destroy, style='Modern.TButton')
                close_btn.pack(fill=tk.X, pady=(15, 0))
            
            def create_card(self, parent, title):
                card = ttk.Frame(parent, style='Card.TFrame', padding=(15, 12))
                card.pack(fill=tk.X, pady=(0, 12))
                
                title_label = ttk.Label(card, text=title, font=('Segoe UI', 11, 'bold'), background='white', foreground='#1d1d1f')
                title_label.pack(anchor=tk.W, pady=(0, 10))
                
                return card
            
            def add_info_row(self, parent, label_text, value_text, value_color=None):
                row_frame = ttk.Frame(parent, style='Card.TFrame')
                row_frame.pack(fill=tk.X, pady=(0, 6))
                
                label = ttk.Label(row_frame, text=f"{label_text}:", font=('Segoe UI', 9), 
                                background='white', foreground='#86868b', width=22, anchor=tk.W)
                label.pack(side=tk.LEFT)
                
                if value_color:
                    value = ttk.Label(row_frame, text=value_text, font=('Segoe UI', 9, 'bold'), 
                                    background='white', foreground=value_color)
                else:
                    value = ttk.Label(row_frame, text=value_text, font=('Segoe UI', 9), 
                                    background='white', foreground='#333333')
                value.pack(side=tk.LEFT)
            
            def format_size(self, size_bytes):
                if size_bytes is None:
                    return '0 字节'
                if size_bytes < 1024:
                    return f"{size_bytes} 字节"
                elif size_bytes < 1024 * 1024:
                    return f"{size_bytes / 1024:.2f} KB"
                elif size_bytes < 1024 * 1024 * 1024:
                    return f"{size_bytes / (1024 * 1024):.2f} MB"
                else:
                    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
        
        root = tk.Tk()
        app = MotionPhotoExtractorApp(root)
        root.mainloop()