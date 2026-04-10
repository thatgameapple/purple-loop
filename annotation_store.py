"""
annotation_store.py
文本标注的持久化存储模块

数据结构（存入 TagStore.files['__annotations__']）：
{
  "/path/to/file.txt": [
    {
      "id": "uuid4",
      "type": "hl_yellow" | "hl_green" | "hl_pink" | "bold" | "underline",
      "start": 123,          ← 字符偏移量（从文本开头算起）
      "end": 145,
      "text": "被标注的文字",  ← 冗余存储，用于面板预览和恢复校验
      "created_at": "2026-04-08T10:00:00",
      "file": "/path/to/file.txt"
    },
    ...
  ]
}
"""

import uuid
from datetime import datetime


class AnnotationStore:
    """管理单个文件的标注集合，委托给外层 TagStore 持久化"""

    ANNOTATION_KEY = '__annotations__'

    def __init__(self, tag_store):
        """
        tag_store: 已有的 TagStore 实例，注解数据存入其 files 字典
        """
        self._store = tag_store

    def _all(self):
        """返回整个注解字典 {filepath: [annotation, ...]}"""
        data = self._store.files.get(self.ANNOTATION_KEY, {})
        if not isinstance(data, dict):
            data = {}
        return data

    def get_for_file(self, filepath):
        """返回指定文件的标注列表（按 start 排序）"""
        all_data = self._all()
        annots = all_data.get(filepath, [])
        return sorted(annots, key=lambda a: a['start'])

    def add(self, filepath, annot_type, start, end, text_content, author=''):
        """
        添加一条标注，返回新建的 annotation dict

        annot_type: 'hl_yellow' | 'hl_green' | 'hl_pink' | 'bold' | 'underline'
        start/end:  字符偏移量（int）
        text_content: 被标注的文字（str）
        author: 作者名（str，可选）
        """
        annot = {
            'id':         str(uuid.uuid4()),
            'type':       annot_type,
            'start':      start,
            'end':        end,
            'text':       text_content,
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'file':       filepath,
        }
        if author:
            annot['author'] = author
        all_data = self._all()
        if filepath not in all_data:
            all_data[filepath] = []
        all_data[filepath].append(annot)
        self._store.files[self.ANNOTATION_KEY] = all_data
        self._store.save()
        return annot

    def remove(self, filepath, annot_id):
        """删除指定 id 的标注"""
        all_data = self._all()
        if filepath in all_data:
            all_data[filepath] = [a for a in all_data[filepath]
                                   if a['id'] != annot_id]
            self._store.files[self.ANNOTATION_KEY] = all_data
            self._store.save()

    def update_note(self, filepath, annot_id, note):
        """更新指定标注的备注内容"""
        all_data = self._all()
        if filepath in all_data:
            for a in all_data[filepath]:
                if a['id'] == annot_id:
                    a['note'] = note
                    break
            self._store.files[self.ANNOTATION_KEY] = all_data
            self._store.save()

    def _restore(self, filepath, annot):
        """将一条标注（已有完整 dict）重新写回存储（用于撤销删除）"""
        all_data = self._all()
        if filepath not in all_data:
            all_data[filepath] = []
        # 避免重复
        ids = {a['id'] for a in all_data[filepath]}
        if annot['id'] not in ids:
            all_data[filepath].append(annot)
            self._store.files[self.ANNOTATION_KEY] = all_data
            self._store.save()

    def change_type(self, filepath, annot_id, new_type):
        """修改标注的颜色类型"""
        all_data = self._all()
        if filepath in all_data:
            for a in all_data[filepath]:
                if a['id'] == annot_id:
                    a['type'] = new_type
                    break
            self._store.files[self.ANNOTATION_KEY] = all_data
            self._store.save()

    def remove_for_file(self, filepath):
        """删除某文件的全部标注"""
        all_data = self._all()
        if filepath in all_data:
            del all_data[filepath]
            self._store.files[self.ANNOTATION_KEY] = all_data
            self._store.save()

    def update_offsets_after_edit(self, filepath, edit_start, delta):
        """
        文本被编辑后更新偏移量（可选，只读阅读器不需要）

        edit_start: 编辑发生的字符偏移量
        delta:      字符数变化量（正=插入，负=删除）
        """
        all_data = self._all()
        if filepath not in all_data:
            return
        updated = []
        for a in all_data[filepath]:
            if a['start'] >= edit_start:
                a = dict(a)
                a['start'] = max(0, a['start'] + delta)
                a['end']   = max(a['start'], a['end'] + delta)
            elif a['end'] > edit_start:
                # 标注跨越编辑点，只延长/缩短末尾
                a = dict(a)
                a['end'] = max(a['start'], a['end'] + delta)
            updated.append(a)
        all_data[filepath] = updated
        self._store.files[self.ANNOTATION_KEY] = all_data
        self._store.save()
