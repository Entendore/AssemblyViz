import sys
import copy
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QLabel, QListWidget, 
                               QListWidgetItem, QPlainTextEdit, QSplitter, 
                               QTableWidget, QTableWidgetItem, QSlider, QGroupBox,
                               QComboBox, QFrame, QDialog, QTextEdit, QInputDialog,
                               QMenu, QLineEdit, QHeaderView, QFileDialog)
from PySide6.QtGui import (QFont, QColor, QTextCharFormat, QTextCursor, QPainter, 
                           QSyntaxHighlighter, QRegularExpression, QPen, QBrush, QPolygonF, QAction)
from PySide6.QtCore import Qt, QTimer, QRect, QSize, QPoint, QPointF
import math
from collections import Counter

# --- INSTRUCTION REFERENCE DATA ---
INSTRUCTION_REF = """
<h2>Pinnacle Edition Instruction Set</h2>
<b>VGA Text Mode (Video Memory):</b><br>
- Memory 0xF00 to 0xF7F is mapped to a 16x8 screen.<br>
- Write ASCII chars here to display them! e.g., <i>MOV [0xF00], 'A'</i><br>
<br>
<b>Hardware Prefixes:</b><br>
- <b>REP</b> : Repeat string instruction ECX times. e.g., <i>REP MOVSB</i><br>
<br>
<b>Assembler Directives:</b><br>
- <b>EQU</b> : Define constant.<br>
- <b>DB, DW, DD</b> : Define data in memory.<br>
<br>
<b>System Calls (INT 0x80):</b><br>
- EAX=1 (Exit), EAX=4 (Write String: EBX=fd, ECX=addr, EDX=len)<br>
<br>
<b>Full ISA:</b><br>
- MOV, ADD, SUB, MUL, DIV, CMP, AND, OR, XOR, SHL, SHR, LEA...<br>
- PUSH, POP, CALL, RET, ENTER, LEAVE, JMP, JE/JNE, JG/JGE, JL/JLE.<br>
- MOVSB, STOSB, LODSB, CMPSB, CMOVZ, CMPXCHG, BT, SETZ.<br>
"""

# --- CPU CYCLE COSTS ---
CYCLES = {
    "MOV": 2, "MOVZX": 3, "MOVSX": 3, "LEA": 2, "ADD": 3, "ADC": 3, "SUB": 3, "SBB": 3, 
    "MUL": 10, "DIV": 20, "INC": 2, "DEC": 2, "CMP": 3, "JMP": 2, "CALL": 4, 
    "RET": 4, "ENTER": 10, "LEAVE": 3, "PUSH": 3, "POP": 3, "PRINT": 1, "AND": 3, "OR": 3, 
    "XOR": 3, "NOT": 1, "SHL": 3, "SHR": 3, "SAR": 4, "ROL": 4, "ROR": 4, "XCHG": 4, 
    "NOP": 1, "CLC": 1, "STC": 1, "CMC": 1, "HLT": 1, "TEST": 3, "SCAN": 50,
    "MOVSB": 5, "STOSB": 5, "LODSB": 5, "CMPSB": 5, "CLD": 1, "STD": 1,
    "PUSHFD": 3, "POPFD": 3, "LOOP": 5, "PUSHAD": 20, "POPAD": 20, "INT": 10,
    "CMOVZ": 2, "CMOVNZ": 2, "CMOVG": 2, "CMOVL": 2, "CMPXCHG": 5, 
    "BT": 4, "SETZ": 3, "SETNZ": 3
}

# --- SYNTAX HIGHLIGHTER ---
class AssemblyHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569cd6"))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = ["MOV", "MOVZX", "MOVSX", "LEA", "ADD", "ADC", "SUB", "SBB", "MUL", "DIV", 
                    "INC", "DEC", "NEG", "CMP", "TEST", "JMP", "JE", "JNE", "JG", "JGE", 
                    "JL", "JLE", "PUSH", "POP", "PUSHFD", "POPFD", "PUSHAD", "POPAD", 
                    "CALL", "RET", "ENTER", "LEAVE", "HLT", "NOP", "XOR", "AND", "OR", "NOT", 
                    "SHL", "SHR", "SAR", "ROL", "ROR", "PRINT", "XCHG", "CLC", "STC", "CMC", 
                    "SCAN", "MOVSB", "STOSB", "LODSB", "CMPSB", "CLD", "STD", "LOOP", "CMOVZ", 
                    "CMOVNZ", "CMOVG", "CMOVL", "CMPXCHG", "BT", "SETZ", "SETNZ", "DB", "DW", "DD", "EQU", "INT", "REP"]
        for word in keywords:
            self.rules.append((QRegularExpression(f"\\b{word}\\b", QRegularExpression.CaseInsensitiveOption), keyword_format))
        
        reg_format = QTextCharFormat()
        reg_format.setForeground(QColor("#4ec9b0"))
        regs = ["RAX", "EAX", "AX", "AL", "AH", "RBX", "EBX", "BX", "BL", "BH", 
                "RCX", "ECX", "CX", "CL", "CH", "RDX", "EDX", "DX", "DL", "DH", 
                "RSI", "ESI", "SI", "RDI", "EDI", "DI", "RSP", "ESP", "SP", "RBP", "EBP", "BP"]
        for reg in regs:
            self.rules.append((QRegularExpression(f"\\b{reg}\\b", QRegularExpression.CaseInsensitiveOption), reg_format))
            
        num_format = QTextCharFormat()
        num_format.setForeground(QColor("#b5cea8"))
        self.rules.append((QRegularExpression("\\b0x[0-9a-fA-F]+\\b|\\b\\d+\\b"), num_format))
        
        str_format = QTextCharFormat()
        str_format.setForeground(QColor("#ce9178"))
        self.rules.append((QRegularExpression("'.'"), str_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6a9955"))
        comment_format.setFontItalic(True)
        self.rules.append((QRegularExpression(";[^\n]*"), comment_format))

    def highlightBlock(self, text):
        for pattern, format in self.rules:
            matchIterator = pattern.globalMatch(text)
            while matchIterator.hasNext():
                match = matchIterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

# --- VISUAL PROFILER CHART WIDGET ---
class ProfileChart(QWidget):
    def __init__(self):
        super().__init__()
        self.data = []
        self.setFixedHeight(80)

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.data: return
        
        max_val = max(d[1] for d in self.data) if self.data else 1
        bar_width = self.width() / max(len(self.data), 1)
        
        for i, (name, count) in enumerate(self.data):
            h = (count / max_val) * (self.height() - 20)
            x = i * bar_width + 5
            y = self.height() - h - 15
            
            painter.setBrush(QColor("#0e639c"))
            painter.setPen(Qt.NoPen)
            painter.drawRect(QRect(x, y, bar_width - 10, h))
            
            painter.setPen(QColor("#d4d4d4"))
            painter.setFont(QFont("Consolas", 8, QFont.Bold))
            painter.drawText(QRect(x, self.height() - 15, bar_width - 10, 15), Qt.AlignCenter, name)

# --- VGA SCREEN WIDGET ---
class VGAScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.memory = []
        self.base_addr = 0xF00
        self.cols = 16
        self.rows = 8
        self.setFixedSize(320, 160)

    def update_mem(self, memory):
        self.memory = memory
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#000000"))
        
        cell_w = self.width() / self.cols
        cell_h = self.height() / self.rows
        
        painter.setFont(QFont("Consolas", 12, QFont.Bold))
        painter.setPen(QColor("#00ff00"))
        
        for r in range(self.rows):
            for c in range(self.cols):
                addr = self.base_addr + (r * self.cols) + c
                if addr < len(self.memory):
                    char_code = self.memory[addr]
                    if 32 <= char_code <= 126:
                        char = chr(char_code)
                    elif char_code == 0:
                        char = " "
                    else:
                        char = " "
                    painter.drawText(QRect(c * cell_w, r * cell_h, cell_w, cell_h), Qt.AlignCenter, char)

# --- BINARY LED MATRIX WIDGET ---
class BinaryLEDWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.value = 0
        self.bits = 32
        self.setFixedHeight(60)

    def set_value(self, val, bits):
        self.value = val & (2**bits - 1)
        self.bits = bits
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        led_size = 10
        spacing = 4
        cols = 32
        total_w = cols * (led_size + spacing) - spacing
        start_x = (self.width() - total_w) / 2
        start_y = 10
        
        for i in range(self.bits):
            r = i // cols
            c = i % cols
            bit_val = (self.value >> (self.bits - 1 - i)) & 1
            x = start_x + c * (led_size + spacing)
            y = start_y + r * (led_size + spacing)
            color = QColor("#00ff00") if bit_val else QColor("#333333")
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(x + led_size/2, y + led_size/2), led_size/2, led_size/2)

# --- FLAG LEDS WIDGET ---
class FlagsLEDWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.flags = {"ZF": 0, "SF": 0, "CF": 0, "OF": 0, "DF": 0}
        self.setFixedHeight(40)

    def set_flags(self, flags):
        self.flags = flags
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        labels = list(self.flags.keys())
        spacing = 60
        
        for i, label in enumerate(labels):
            x = 10 + i * spacing
            y = 10
            color = QColor("#ff3333") if self.flags[label] == 1 else QColor("#444444")
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(x + 5, y + 5), 5, 5)
            
            painter.setPen(QColor("#d4d4d4"))
            painter.setFont(QFont("Consolas", 9, QFont.Bold))
            painter.drawText(QRect(x + 15, y, 40, 15), Qt.AlignLeft | Qt.AlignVCenter, label)

# --- CPU SCHEMATIC WIDGET ---
class CPUArchitectureWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(140)
        self.active_bus = None
        self.decode_text = ""
        self.exec_duration = 200
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.clear_bus)

    def animate(self, flow_type, decode_text, cycles):
        self.active_bus = flow_type
        self.decode_text = decode_text
        self.exec_duration = min(cycles * 50, 1000)
        self.update()
        self.timer.start(400 + self.exec_duration)

    def clear_bus(self):
        self.active_bus = None
        self.decode_text = ""
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect_ctrl = QRect(270, 10, 120, 30)
        rect_reg = QRect(50, 60, 120, 50)
        rect_alu = QRect(270, 60, 120, 50)
        rect_mem = QRect(490, 60, 120, 50)
        
        painter.setPen(QColor("#888"))
        painter.setBrush(QColor("#252526"))
        painter.drawRoundedRect(rect_ctrl, 5, 5)
        painter.drawRoundedRect(rect_reg, 5, 5)
        painter.drawRoundedRect(rect_alu, 5, 5)
        painter.drawRoundedRect(rect_mem, 5,5)
        
        painter.setPen(QColor("#d4d4d4"))
        painter.drawText(rect_ctrl, Qt.AlignCenter, "CONTROL (EIP)")
        painter.drawText(rect_reg, Qt.AlignCenter, "REGISTERS")
        painter.drawText(rect_alu, Qt.AlignCenter, "ALU")
        painter.drawText(rect_mem, Qt.AlignCenter, "MEMORY (4KB)")

        def draw_bus(name, p1, p2):
            pen = QPen(QColor("#3a3a3a"), 3)
            if self.active_bus == name:
                pen.setColor(QColor("#00ff00"))
                pen.setWidth(4)
            painter.setPen(pen)
            painter.drawLine(p1, p2)
            angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            arrow_size = 8
            p3 = QPointF(p2.x() - arrow_size * math.cos(angle - math.pi/6), p2.y() - arrow_size * math.sin(angle - math.pi/6))
            p4 = QPointF(p2.x() - arrow_size * math.cos(angle + math.pi/6), p2.y() - arrow_size * math.sin(angle + math.pi/6))
            painter.setBrush(pen.color())
            painter.drawPolygon(QPolygonF([p2, p3, p4]))

        draw_bus("MEM_REG", QPointF(490, 85), QPointF(170, 85))
        draw_bus("REG_ALU", QPointF(170, 75), QPointF(270, 75))
        draw_bus("ALU_REG", QPointF(270, 95), QPointF(170, 95))
        draw_bus("IMM_REG", QPointF(110, 10), QPointF(110, 60))
        draw_bus("CTRL", QPointF(330, 40), QPointF(330, 60))

# --- CUSTOM CODE EDITOR ---
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.editor.show_line_menu)

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            line = self.editor.cursorForPosition(QPoint(0, event.pos().y())).blockNumber() + 1
            if line in self.editor.breakpoints:
                self.editor.breakpoints.remove(line)
            else:
                self.editor.breakpoints.add(line)
            self.update()

class CodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.breakpoints = set()
        self.exec_counts = {}
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        self.setFont(QFont("Consolas", 11))
        self.highlighter = AssemblyHighlighter(self.document())

    def line_number_area_width(self):
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num /= 10
            digits += 1
        space = 25 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def highlight_current_line(self, line_num):
        self.setExtraSelections([])
        if line_num <= 0 or line_num > self.blockCount(): return
        block = self.document().findBlockByNumber(line_num - 1)
        if not block.isValid(): return
        cursor = QTextCursor(block)
        selection = QPlainTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#cca300"))
        selection.format.setProperty(QTextCharFormat.FullWidthSelection, True)
        selection.cursor = cursor
        self.setExtraSelections([selection])

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#252526"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                count = self.exec_counts.get(block_number + 1, 0)
                intensity = min(count / 10.0, 1.0)
                r = int(136 + (255 - 136) * intensity)
                g = int(136 + (140 - 136) * intensity)
                b = int(136 + (0 - 136) * intensity)
                painter.setPen(QColor(r, g, b))
                painter.drawText(20, top, self.line_number_area.width(), self.fontMetrics().height(), Qt.AlignLeft, number)
                
                if (block_number + 1) in self.breakpoints:
                    painter.setBrush(QColor("#f44747"))
                    painter.setPen(QColor("#f44747"))
                    radius = self.fontMetrics().height() / 2 - 2
                    center_y = top + self.fontMetrics().height() / 2
                    painter.drawEllipse(QPointF(10, center_y), radius, radius)
                    
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1
            
    def show_line_menu(self, pos):
        line = self.cursorForPosition(QPoint(0, pos.y())).blockNumber() + 1
        menu = QMenu(self)
        action = menu.addAction(f"Run to Line {line}")
        chosen = menu.exec(self.line_number_area.mapToGlobal(pos))
        if chosen == action:
            if hasattr(self, 'run_to_line_callback'):
                self.run_to_line_callback(line)

# --- SANDBOX CPU EMULATOR ---
class SandboxCPU:
    def __init__(self):
        self.memory = [0] * 4096 # 4KB Total Memory
        self.mode = 32
        self.history = []
        self.instructions_executed = 0
        self.total_cycles = 0
        self.exec_counts = {}
        self.instr_profile = Counter()
        self.scan_input_buffer = None
        self.set_mode(32)

    def set_mode(self, bits):
        self.mode = bits
        self.mask = {16: 0xFFFF, 32: 0xFFFFFFFF, 64: 0xFFFFFFFFFFFFFFFF}[bits]
        self.ip_name = {16: "IP", 32: "EIP", 64: "RIP"}[bits]
        self.word_size = bits // 8
        regs_16 = ["AX", "BX", "CX", "DX", "SI", "DI", "SP", "BP"]
        regs_32 = ["EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "ESP", "EBP"]
        regs_64 = ["RAX", "RBX", "RCX", "RDX", "RSI", "RDI", "RSP", "RBP"]
        self.valid_regs = {16: regs_16, 32: regs_32, 64: regs_64}[bits]
        self.reset()

    def reset(self):
        self.registers = {r: 0 for r in self.valid_regs}
        self.registers[self.valid_regs[6]] = 0x800 # ESP starts at 2KB (middle of mem)
        self.registers[self.valid_regs[7]] = 0x800 
        self.flags = {"ZF": 0, "SF": 0, "CF": 0, "OF": 0, "DF": 0}
        self.memory = [0] * 4096
        self.eip = 1
        self.labels = {}
        self.data_labels = set()
        self.symbols = []
        self.code = []
        self.halted = False
        self.history = []
        self.instructions_executed = 0
        self.total_cycles = 0
        self.exec_counts = {}
        self.instr_profile = Counter()
        self.scan_input_buffer = None

    def load_code(self, code_text):
        self.reset()
        raw_lines = code_text.split('\n')
        code_lines = []
        data_ptr = 0
        
        for line in raw_lines:
            line = line.split(';')[0].strip()
            if not line: continue
            
            parts = line.replace(',', ' ').split()
            if len(parts) >= 3 and parts[1].upper() == 'EQU':
                self.labels[parts[0]] = int(parts[2], 0)
                self.symbols.append(("Const", parts[0], int(parts[2], 0)))
            elif len(parts) >= 2 and parts[1].upper() in ['DB', 'DW', 'DD']:
                label = parts[0].replace(':', '')
                self.labels[label] = data_ptr
                self.data_labels.add(label)
                
                size = {'DB': 1, 'DW': 2, 'DD': 4}[parts[1].upper()]
                start_ptr = data_ptr
                for val_str in parts[2:]:
                    try:
                        if val_str.startswith("'") and val_str.endswith("'"):
                            val = ord(val_str[1])
                        else:
                            val = int(val_str, 0)
                        for i in range(size):
                            self.memory[data_ptr] = (val >> (8*i)) & 0xFF
                            data_ptr += 1
                    except ValueError:
                        pass
                self.symbols.append(("Data", label, start_ptr))
            else:
                code_lines.append(line)
                
        actual_line_num = 0
        for line in code_lines:
            if not line: continue
            actual_line_num += 1
            if line.endswith(':'):
                lbl = line[:-1].strip()
                self.labels[lbl] = actual_line_num
                self.code.append(f"LABEL {lbl}")
                self.symbols.append(("Code", lbl, actual_line_num))
            else:
                self.code.append(line)

    def get_reg_info(self, name):
        name = name.upper()
        if name in self.valid_regs:
            return name, self.mask, 0
        mapping = {
            "AL": ("AX", 0xFF, 0), "AH": ("AX", 0xFF, 8),
            "BL": ("BX", 0xFF, 0), "BH": ("BX", 0xFF, 8),
            "CL": ("CX", 0xFF, 0), "CH": ("CX", 0xFF, 8),
            "DL": ("DX", 0xFF, 0), "DH": ("DX", 0xFF, 8),
            "AX": ("AX", 0xFFFF, 0), "BX": ("BX", 0xFFFF, 0),
            "CX": ("CX", 0xFFFF, 0), "DX": ("DX", 0xFFFF, 0),
            "SI": ("SI", 0xFFFF, 0), "DI": ("DI", 0xFFFF, 0),
            "SP": ("SP", 0xFFFF, 0), "BP": ("BP", 0xFFFF, 0)
        }
        if name in mapping:
            base_short, mask, shift = mapping[name]
            if self.mode == 16: base_reg = base_short
            elif self.mode == 32: base_reg = "E" + base_short
            else: base_reg = "R" + base_short
            return base_reg, mask, shift
        return None, None, None

    def _read_mem(self, addr, size):
        val = 0
        for i in range(size):
            val |= self.memory[(addr + i) % 4096] << (8 * i)
        return val

    def _write_mem(self, addr, val, size):
        for i in range(size):
            self.memory[(addr + i) % 4096] = (val >> (8 * i)) & 0xFF

    def _resolve_mem_addr(self, token, alu_trace):
        inner = token.strip('[]').replace(' ', '')
        base_val = 0
        off_val = 0
        
        if '+' in inner:
            base, offset = inner.split('+')
            base_val = self.labels[base] if base in self.data_labels else self._get_value(base)[0]
            off_val = int(offset, 0)
            addr = (base_val + off_val) % 4096
            alu_trace += f"ADDR = 0x{base_val:X} + 0x{off_val:X} = 0x{addr:X}"
        elif '-' in inner:
            base, offset = inner.split('-')
            base_val = self.labels[base] if base in self.data_labels else self._get_value(base)[0]
            off_val = int(offset, 0)
            addr = (base_val - off_val) % 4096
            alu_trace += f"ADDR = 0x{base_val:X} - 0x{off_val:X} = 0x{addr:X}"
        else:
            if inner in self.data_labels:
                addr = self.labels[inner] % 4096
            elif inner.upper() in self.valid_regs:
                addr = self._get_value(inner)[0] % 4096
            else:
                addr = int(inner, 0) % 4096
            alu_trace += f"ADDR = 0x{addr:X}"
        return addr, alu_trace

    def _get_value(self, token, size=4, alu_trace=""):
        token = token.strip()
        if token.startswith('['):
            addr, alu_trace = self._resolve_mem_addr(token, alu_trace)
            return self._read_mem(addr, size), alu_trace
            
        if token in self.labels:
            return self.labels[token], alu_trace

        base, mask, shift = self.get_reg_info(token)
        if base:
            return (self.registers[base] >> shift) & mask, alu_trace
        return int(token, 0), alu_trace

    def _set_value(self, token, val):
        base, mask, shift = self.get_reg_info(token)
        if base:
            current = self.registers[base]
            cleared = current & ~(mask << shift)
            self.registers[base] = cleared | ((val & mask) << shift)
            return base
        else:
            raise Exception(f"Invalid register: {token}")

    def save_state(self):
        self.history.append({
            "registers": copy.deepcopy(self.registers),
            "flags": copy.deepcopy(self.flags),
            "memory": copy.deepcopy(self.memory),
            "eip": self.eip,
            "halted": self.halted,
            "instr_count": self.instructions_executed,
            "cycles": self.total_cycles,
            "exec_counts": copy.deepcopy(self.exec_counts),
            "instr_profile": copy.deepcopy(self.instr_profile)
        })

    def restore_state(self):
        if self.history:
            state = self.history.pop()
            self.registers = state["registers"]
            self.flags = state["flags"]
            self.memory = state["memory"]
            self.eip = state["eip"]
            self.halted = state["halted"]
            self.instructions_executed = state["instr_count"]
            self.total_cycles = state["cycles"]
            self.exec_counts = state["exec_counts"]
            self.instr_profile = state["instr_profile"]
            return True
        return False

    def step(self):
        if self.halted:
            return {"msg": "CPU Halted.", "dest_reg": None, "flow": None, "print": None, "cycles": 0, "scan": False, "alu_trace": "", "decode": "", "instr": "HLT", "line_num": 0}
        
        while self.eip <= len(self.code) and self.code[self.eip - 1].startswith("LABEL "):
            self.eip += 1

        if self.eip > len(self.code):
            self.halted = True
            return {"msg": "CPU Halted. End of program.", "dest_reg": None, "flow": None, "print": None, "cycles": 0, "scan": False, "alu_trace": "", "decode": "", "instr": "End", "line_num": 0}

        self.save_state()
        self.instructions_executed += 1
        self.exec_counts[self.eip] = self.exec_counts.get(self.eip, 0) + 1
        
        instruction = self.code[self.eip - 1]
        parts = instruction.replace(',', ' ').split()
        cmd = parts[0].upper()
        self.instr_profile[cmd] += 1
        
        msg = f"Executed: {instruction}"
        next_eip = self.eip + 1
        dest_reg = None
        print_val = None
        flow = None
        is_scan = False
        alu_trace = ""
        decode_text = f"Op: {cmd}\nArgs: {', '.join(parts[1:])}"
        cycles = CYCLES.get(cmd, 1)

        try:
            # Handle REP prefix
            if cmd == "REP":
                actual_cmd = parts[1].upper()
                cx_reg = self.valid_regs[2]
                count = self.registers[cx_reg]
                decode_text = f"REP {actual_cmd}\nRepeating {count} times"
                cycles = CYCLES[actual_cmd] * count
                
                if actual_cmd in ["MOVSB", "STOSB", "LODSB", "CMPSB"]:
                    flow = "MEM_REG"
                    si_reg = self.valid_regs[4] 
                    di_reg = self.valid_regs[5] 
                    step = -1 if self.flags["DF"] == 1 else 1
                    
                    for _ in range(count):
                        si_addr = self.registers[si_reg] % 4096
                        di_addr = self.registers[di_reg] % 4096
                        
                        if actual_cmd == "MOVSB":
                            self.memory[di_addr] = self.memory[si_addr]
                        elif actual_cmd == "STOSB":
                            al_val = self._get_value("AL")[0]
                            self.memory[di_addr] = al_val
                        elif actual_cmd == "LODSB":
                            dest_reg = self._set_value("AL", self.memory[si_addr])
                        elif actual_cmd == "CMPSB":
                            res = self.memory[si_addr] - self.memory[di_addr]
                            self.flags["ZF"] = 1 if res == 0 else 0
                            self.flags["SF"] = 1 if res < 0 else 0
                            if self.flags["ZF"] == 0: break # REPNE behavior
                    
                        self.registers[si_reg] = (self.registers[si_reg] + step) & self.mask
                        self.registers[di_reg] = (self.registers[di_reg] + step) & self.mask
                        self.registers[cx_reg] -= 1
                    alu_trace += f"Repeated {actual_cmd} {count} times."

            elif cmd == "INT":
                flow = "CTRL"
                int_num = int(parts[1], 0)
                if int_num == 0x80:
                    sys_call = self.registers[self.valid_regs[0]] 
                    if sys_call == 1: 
                        self.halted = True
                        msg = "Syscall: Exit"
                    elif sys_call == 4: 
                        str_addr = self.registers[self.valid_regs[2]] 
                        length = self.registers[self.valid_regs[3]] 
                        s = ""
                        for i in range(length):
                            s += chr(self.memory[(str_addr + i) % 4096])
                        print_val = s
                        msg = "Syscall: Write String"
            elif cmd in ["MOV", "MOVZX", "MOVSX", "LEA"]:
                dest = parts[1]
                _, dest_mask, _ = self.get_reg_info(dest)
                dest_size = (dest_mask.bit_length() + 7) // 8
                
                if cmd == "LEA":
                    inner = parts[2].strip('[]').replace(' ', '')
                    if '+' in inner:
                        base, offset = inner.split('+')
                        base_val = self.labels[base] if base in self.data_labels else self._get_value(base)[0]
                        val = (base_val + int(offset, 0)) % 4096
                    elif '-' in inner:
                        base, offset = inner.split('-')
                        base_val = self.labels[base] if base in self.data_labels else self._get_value(base)[0]
                        val = (base_val - int(offset, 0)) % 4096
                    else:
                        val = self.labels[inner] if inner in self.data_labels else self._get_value(inner)[0]
                    dest_reg = self._set_value(dest, val)
                    alu_trace = f"ADDR = 0x{val:X}"
                else:
                    _, src_mask, _ = self.get_reg_info(parts[2])
                    read_size = (src_mask.bit_length() + 7) // 8 if src_mask else dest_size
                    val, alu_trace = self._get_value(parts[2], size=read_size, alu_trace=alu_trace)
                
                if dest.startswith('['):
                    addr, alu_trace = self._resolve_mem_addr(dest, alu_trace)
                    self._write_mem(addr, val, dest_size)
                    flow = "REG_ALU"
                else:
                    if cmd == "MOVZX":
                        val = val & src_mask
                        decode_text += f"\nMicro: Zero Extend 0x{val:X}"
                    elif cmd == "MOVSX":
                        sign_bit = src_mask // 2 + 1
                        if val & sign_bit:
                            val = val | (~src_mask & self.mask)
                        decode_text += f"\nMicro: Sign Extend 0x{val:X}"
                    dest_reg = self._set_value(dest, val)
                    flow = "IMM_REG"
            elif cmd == "SCAN":
                is_scan = True
                flow = "IMM_REG"
            elif cmd == "PRINT":
                print_val, alu_trace = self._get_value(parts[1], size=self.word_size, alu_trace=alu_trace)
                msg = f"Printed: {parts[1]} = {print_val}"
                flow = "IMM_REG"
            elif cmd in ["ADD", "ADC", "SUB", "SBB", "AND", "OR", "XOR", "MUL", "DIV", "INC", "DEC", "CMP", "TEST", "SHL", "SHR", "SAR", "ROL", "ROR", "NEG", "NOT", "BT"]:
                flow = "ALU_REG"
                _, mask, _ = self.get_reg_info(parts[1])
                msb = mask // 2 + 1
                curr, alu_trace = self._get_value(parts[1], alu_trace=alu_trace)
                alu_trace += f"\nALU: 0x{curr & mask:X} "
                
                if cmd == "MUL":
                    val, alu_trace = self._get_value(parts[2], alu_trace=alu_trace)
                    alu_trace += f"* 0x{val & mask:X} "
                    res = self.registers[self.valid_regs[0]] * val
                    self.registers[self.valid_regs[0]] = res & self.mask
                    dest_reg = self.valid_regs[0]
                elif cmd == "DIV":
                    val, alu_trace = self._get_value(parts[2], alu_trace=alu_trace)
                    if val == 0: raise Exception("Divide by zero")
                    alu_trace += f"/ 0x{val & mask:X} "
                    self.registers[self.valid_regs[0]] = (self.registers[self.valid_regs[0]] // val) & self.mask
                    dest_reg = self.valid_regs[0]
                else:
                    val, alu_trace = self._get_value(parts[2], alu_trace=alu_trace) if len(parts) > 2 else (0, alu_trace)
                    cf = self.flags["CF"]
                    
                    if cmd == "ADD": 
                        res = curr + val
                        self.flags["CF"] = 1 if res > mask else 0
                        alu_trace += f"+ 0x{val & mask:X} "
                    elif cmd == "ADC":
                        res = curr + val + cf
                        self.flags["CF"] = 1 if res > mask else 0
                        alu_trace += f"+ 0x{val & mask:X} + CF({cf}) "
                    elif cmd == "SUB": 
                        res = curr - val
                        self.flags["CF"] = 1 if curr < val else 0
                        alu_trace += f"- 0x{val & mask:X} "
                    elif cmd == "SBB":
                        res = curr - val - cf
                        self.flags["CF"] = 1 if curr < (val + cf) else 0
                        alu_trace += f"- 0x{val & mask:X} - CF({cf}) "
                    elif cmd == "AND": res = curr & val
                    elif cmd == "OR": res = curr | val
                    elif cmd == "XOR": res = curr ^ val
                    elif cmd == "INC": res = curr + 1
                    elif cmd == "DEC": res = curr - 1
                    elif cmd == "NEG": 
                        res = -curr
                        self.flags["CF"] = 1 if curr != 0 else 0
                    elif cmd == "NOT": res = ~curr
                    elif cmd in ["SHL", "SHR", "SAR", "ROL", "ROR"]:
                        val = val % self.mode
                        if cmd == "SHL": res = (curr << val) & mask
                        elif cmd == "SHR": res = (curr & mask) >> val
                        elif cmd == "SAR":
                            signed = curr if curr < msb else curr - (mask + 1)
                            res = (signed >> val) & mask
                        elif cmd == "ROL": res = ((curr << val) | (curr >> (self.mode - val))) & mask
                        elif cmd == "ROR": res = ((curr >> val) | (curr << (self.mode - val))) & mask
                    elif cmd == "BT":
                        bit = val % self.mode
                        self.flags["CF"] = (curr >> bit) & 1
                        res = curr 
                        alu_trace += f"Test Bit {bit} -> CF={self.flags['CF']}"

                    if cmd in ["CMP", "TEST"]:
                        res = (curr - val) if cmd == "CMP" else (curr & val)
                    elif cmd != "BT":
                        dest_reg = self._set_value(parts[1], res)
                    
                    if cmd not in ["NOT", "SHL", "SHR", "SAR", "ROL", "ROR", "BT"]:
                        self.flags["ZF"] = 1 if (res & mask) == 0 else 0
                        self.flags["SF"] = 1 if (res & msb) != 0 else 0
                        
                alu_trace += f"= 0x{res & mask:X}"
                
            elif cmd in ["CMOVZ", "CMOVNZ", "CMOVG", "CMOVL", "SETZ", "SETNZ", "CMPXCHG"]:
                flow = "ALU_REG"
                if cmd.startswith("CMOV"):
                    condition = False
                    if cmd == "CMOVZ" and self.flags["ZF"] == 1: condition = True
                    elif cmd == "CMOVNZ" and self.flags["ZF"] == 0: condition = True
                    elif cmd == "CMOVG" and self.flags["ZF"] == 0 and self.flags["SF"] == 0: condition = True
                    elif cmd == "CMOVL" and self.flags["SF"] == 1: condition = True
                    
                    if condition:
                        val, alu_trace = self._get_value(parts[2], alu_trace=alu_trace)
                        dest_reg = self._set_value(parts[1], val)
                        decode_text += f"\nCondition TRUE. Move executed."
                    else:
                        decode_text += f"\nCondition FALSE. Move skipped."
                elif cmd.startswith("SET"):
                    val = 1
                    if cmd == "SETZ" and self.flags["ZF"] == 0: val = 0
                    if cmd == "SETNZ" and self.flags["ZF"] == 1: val = 0
                    dest_reg = self._set_value(parts[1], val)
                    alu_trace = f"Set to {val} based on flags."
                elif cmd == "CMPXCHG":
                    dest_val, alu_trace = self._get_value(parts[1], alu_trace=alu_trace)
                    src_val, alu_trace = self._get_value(parts[2], alu_trace=alu_trace)
                    acc_name = self.valid_regs[0]
                    
                    if self.registers[acc_name] == dest_val:
                        if parts[1].startswith('['):
                            addr, _ = self._resolve_mem_addr(parts[1], "")
                            self._write_mem(addr, src_val, self.word_size)
                        else:
                            self._set_value(parts[1], src_val)
                        self.flags["ZF"] = 1
                        alu_trace += f"\nMatch! Swapped with {parts[2]}."
                    else:
                        self.registers[acc_name] = dest_val
                        self.flags["ZF"] = 0
                        alu_trace += f"\nNo match. {acc_name} updated to 0x{dest_val:X}."

            elif cmd in ["MOVSB", "STOSB", "LODSB", "CMPSB"]:
                flow = "MEM_REG"
                si_reg = self.valid_regs[4] 
                di_reg = self.valid_regs[5] 
                step = -1 if self.flags["DF"] == 1 else 1
                decode_text = f"Op: {cmd}\nDF={self.flags['DF']} (Step {step})"
                
                si_addr = self.registers[si_reg] % 4096
                di_addr = self.registers[di_reg] % 4096
                
                if cmd == "MOVSB":
                    self.memory[di_addr] = self.memory[si_addr]
                    decode_text += f"\n1. MEM[{di_addr}] = MEM[{si_addr}]"
                elif cmd == "STOSB":
                    al_val = self._get_value("AL")[0]
                    self.memory[di_addr] = al_val
                    decode_text += f"\n1. MEM[{di_addr}] = AL(0x{al_val:X})"
                elif cmd == "LODSB":
                    dest_reg = self._set_value("AL", self.memory[si_addr])
                    decode_text += f"\n1. AL = MEM[{si_addr}]"
                elif cmd == "CMPSB":
                    res = self.memory[si_addr] - self.memory[di_addr]
                    self.flags["ZF"] = 1 if res == 0 else 0
                    self.flags["SF"] = 1 if res < 0 else 0
                    decode_text += f"\n1. CMP MEM[{si_addr}], MEM[{di_addr}]"
                
                self.registers[si_reg] = (self.registers[si_reg] + step) & self.mask
                self.registers[di_reg] = (self.registers[di_reg] + step) & self.mask
                decode_text += f"\n2. {si_reg} += {step}, {di_reg} += {step}"

            elif cmd == "XCHG":
                r1, r2 = parts[1], parts[2]
                v1, alu_trace = self._get_value(r1, alu_trace=alu_trace)
                v2, alu_trace = self._get_value(r2, alu_trace=alu_trace)
                if r1.startswith('['):
                    addr, _ = self._resolve_mem_addr(r1, "")
                    self._write_mem(addr, v2, self.word_size)
                else:
                    self._set_value(r1, v2)
                if r2.startswith('['):
                    addr, _ = self._resolve_mem_addr(r2, "")
                    self._write_mem(addr, v1, self.word_size)
                else:
                    self._set_value(r2, v1)
                dest_reg = self.get_reg_info(r1)[0] if not r1.startswith('[') else self.get_reg_info(r2)[0]
                flow = "REG_ALU"
                
            elif cmd in ["PUSH", "POP", "PUSHFD", "POPFD", "PUSHAD", "POPAD", "CALL", "RET", "ENTER", "LEAVE", "LOOP"]:
                flow = "MEM_REG"
                sp_reg = self.valid_regs[6]
                bp_reg = self.valid_regs[7]
                ws = self.word_size
                
                if cmd in ["PUSH", "PUSHFD"]:
                    self.registers[sp_reg] -= ws
                    addr = self.registers[sp_reg] % 4096
                    val = self._get_value(parts[1])[0] if cmd == "PUSH" else (self.flags["ZF"] | (self.flags["SF"]<<1) | (self.flags["CF"]<<2) | (self.flags["OF"]<<3) | (self.flags["DF"]<<4))
                    self._write_mem(addr, val, ws)
                elif cmd in ["POP", "POPFD"]:
                    addr = self.registers[sp_reg] % 4096
                    val = self._read_mem(addr, ws)
                    if cmd == "POP": 
                        dest_reg = self._set_value(parts[1], val)
                    else:
                        self.flags["ZF"] = val & 1
                        self.flags["SF"] = (val >> 1) & 1
                        self.flags["CF"] = (val >> 2) & 1
                        self.flags["OF"] = (val >> 3) & 1
                        self.flags["DF"] = (val >> 4) & 1
                    self.registers[sp_reg] += ws
                elif cmd == "PUSHAD":
                    for r in self.valid_regs:
                        self.registers[sp_reg] -= ws
                        self._write_mem(self.registers[sp_reg], self.registers[r], ws)
                    decode_text += f"\nPushed all 8 registers."
                elif cmd == "POPAD":
                    for r in reversed(self.valid_regs):
                        self.registers[r] = self._read_mem(self.registers[sp_reg], ws)
                        self.registers[sp_reg] += ws
                    decode_text += f"\nPopped all 8 registers."
                elif cmd == "ENTER":
                    size = int(parts[1], 0)
                    self.registers[sp_reg] -= ws
                    self._write_mem(self.registers[sp_reg], self.registers[bp_reg], ws)
                    self.registers[bp_reg] = self.registers[sp_reg]
                    self.registers[sp_reg] -= size
                    decode_text += f"\nFrame set. Allocated {size} local bytes."
                elif cmd == "LEAVE":
                    self.registers[sp_reg] = self.registers[bp_reg]
                    addr = self.registers[sp_reg] % 4096
                    self.registers[bp_reg] = self._read_mem(addr, ws)
                    self.registers[sp_reg] += ws
                    decode_text += f"\nFrame torn down."
                elif cmd == "CALL":
                    self.registers[sp_reg] -= ws
                    self._write_mem(self.registers[sp_reg], next_eip, ws)
                    next_eip = self.labels.get(parts[1], int(parts[1], 0))
                elif cmd == "RET":
                    addr = self.registers[sp_reg] % 4096
                    next_eip = self._read_mem(addr, ws)
                    self.registers[sp_reg] += ws
                    if len(parts) > 1:
                        pop_bytes = int(parts[1], 0)
                        self.registers[sp_reg] += pop_bytes
                        alu_trace += f"\nCleaned {pop_bytes} bytes from stack."
                elif cmd == "LOOP":
                    cx_reg = self.valid_regs[2] 
                    self.registers[cx_reg] -= 1
                    if self.registers[cx_reg] > 0:
                        next_eip = self.labels.get(parts[1], int(parts[1], 0))
                    decode_text += f"\n{cx_reg} decremented to {self.registers[cx_reg]}"
            elif cmd in ["JMP", "JE", "JNE", "JG", "JGE", "JL", "JLE"]:
                flow = "CTRL"
                target = self.labels.get(parts[1], int(parts[1], 0))
                if cmd == "JMP": next_eip = target
                elif cmd == "JE" and self.flags["ZF"] == 1: next_eip = target
                elif cmd == "JNE" and self.flags["ZF"] == 0: next_eip = target
                elif cmd == "JG" and self.flags["ZF"] == 0 and self.flags["SF"] == 0: next_eip = target
                elif cmd == "JGE" and self.flags["SF"] == 0: next_eip = target
                elif cmd == "JL" and self.flags["SF"] == 1: next_eip = target
                elif cmd == "JLE" and (self.flags["ZF"] == 1 or self.flags["SF"] == 1): next_eip = target
            elif cmd in ["NOP", "CLC", "STC", "CMC", "CLD", "STD", "HLT"]: 
                if cmd == "HLT": self.halted = True
                elif cmd == "CLC": self.flags["CF"] = 0
                elif cmd == "STC": self.flags["CF"] = 1
                elif cmd == "CMC": self.flags["CF"] = 1 - self.flags["CF"]
                elif cmd == "CLD": self.flags["DF"] = 0
                elif cmd == "STD": self.flags["DF"] = 1
            else:
                raise Exception(f"Unknown instruction: {cmd}")
            
            self.eip = next_eip
        except Exception as e:
            self.halted = True
            msg = f"Error: {str(e)}"

        return {"msg": msg, "dest_reg": dest_reg, "flow": flow, "print": print_val, "cycles": cycles, "scan": is_scan, "alu_trace": alu_trace, "decode": decode_text, "instr": instruction, "line_num": self.eip - 1}

# --- MAIN GUI ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pinnacle Edition: 4KB Architecture & VGA")
        self.resize(1400, 950)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")

        self.cpu = SandboxCPU()
        self.is_running = False
        self.view_mode = "Hex"
        self.mem_view_mode = 0 
        self.mem_page = 0 # 0=Data, 1=Stack, 2=Video
        self.last_modified_reg = None
        self.step_over_target = None
        self.step_out_target = -1
        self.is_updating_ui = False
        self.current_file = None
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step_cpu)
        self.flash_timer = QTimer(self)
        self.flash_timer.setSingleShot(True)
        self.flash_timer.timeout.connect(self.clear_flash)

        self.setup_ui()
        self.setup_menu()
        self.on_mode_changed(1) # 32-bit

    def setup_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open...", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("Save As...", self)
        save_as_action.triggered.connect(self.save_as_file)
        file_menu.addAction(save_as_action)

    def open_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Open Assembly File", "", "Assembly Files (*.asm);;All Files (*)")
        if fname:
            with open(fname, 'r') as f:
                self.code_editor.setPlainText(f.read())
            self.current_file = fname
            self.load_code()

    def save_file(self):
        if self.current_file:
            with open(self.current_file, 'w') as f:
                f.write(self.code_editor.toPlainText())
        else:
            self.save_as_file()

    def save_as_file(self):
        fname, _ = QFileDialog.getSaveFileName(self, "Save Assembly File", "", "Assembly Files (*.asm);;All Files (*)")
        if fname:
            with open(fname, 'w') as f:
                f.write(self.code_editor.toPlainText())
            self.current_file = fname

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- ARCHITECTURE VIZ ---
        arch_group = QGroupBox("CPU Architecture & Micro-Op Decode")
        arch_layout = QVBoxLayout(arch_group)
        self.arch_viz = CPUArchitectureWidget()
        arch_layout.addWidget(self.arch_viz)
        main_layout.addWidget(arch_group)

        # --- TOP CONFIG BAR ---
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Mode:</b>"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["16-bit", "32-bit", "64-bit"])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        top_bar.addWidget(self.mode_combo)

        top_bar.addWidget(QLabel("<b>View:</b>"))
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Hex", "Dec", "Bin"])
        self.view_combo.currentIndexChanged.connect(self.on_view_changed)
        top_bar.addWidget(self.view_combo)
        
        self.btn_help = QPushButton("📖 Instructions")
        self.btn_help.setStyleSheet("background-color: #3a3a3a; padding: 4px;")
        self.btn_help.clicked.connect(self.show_help)
        top_bar.addWidget(self.btn_help)
        
        self.stats_label = QLabel("Cycles: 0 | Instr: 0 | CPI: 0.0 | Time: 0.00 ns")
        self.stats_label.setStyleSheet("color: #b5cea8; font-weight: bold;")
        top_bar.addStretch()
        top_bar.addWidget(self.stats_label)
        main_layout.addLayout(top_bar)

        # --- MAIN SPLITTER ---
        splitter = QSplitter(Qt.Horizontal)
        
        # Left Splitter (Code + Trace + Profiler)
        left_splitter = QSplitter(Qt.Vertical)
        self.code_editor = CodeEditor()
        self.code_editor.run_to_line_callback = self.run_to_line
        left_splitter.addWidget(self.code_editor)
        
        bottom_left_splitter = QSplitter(Qt.Horizontal)
        
        trace_group = QGroupBox("Execution Trace")
        trace_layout = QVBoxLayout(trace_group)
        self.trace_list = QListWidget()
        self.trace_list.setFont(QFont("Consolas", 10))
        self.trace_list.setStyleSheet("background-color: #1a1a1a;")
        trace_layout.addWidget(self.trace_list)
        bottom_left_splitter.addWidget(trace_group)
        
        sym_group = QGroupBox("Symbol Table")
        sym_layout = QVBoxLayout(sym_group)
        self.sym_list = QListWidget()
        self.sym_list.setFont(QFont("Consolas", 10))
        self.sym_list.setStyleSheet("background-color: #1a1a1a;")
        sym_layout.addWidget(self.sym_list)
        bottom_left_splitter.addWidget(sym_group)
        
        left_splitter.addWidget(bottom_left_splitter)
        
        prof_group = QGroupBox("Instruction Profiler")
        prof_layout = QVBoxLayout(prof_group)
        self.profile_chart = ProfileChart()
        prof_layout.addWidget(self.profile_chart)
        left_splitter.addWidget(prof_group)
        
        left_splitter.setSizes([300, 150, 80])
        splitter.addWidget(left_splitter)

        # Right Splitter (CPU State)
        right_splitter = QSplitter(Qt.Vertical)
        
        reg_group = QGroupBox("Registers & Accumulator LEDs")
        reg_layout = QVBoxLayout(reg_group)
        self.led_widget = BinaryLEDWidget()
        reg_layout.addWidget(self.led_widget)
        self.reg_list = QListWidget()
        self.reg_list.setFont(QFont("Consolas", 11))
        self.reg_list.setStyleSheet("background-color: #252526;")
        reg_layout.addWidget(self.reg_list)
        self.flags_widget = FlagsLEDWidget()
        reg_layout.addWidget(self.flags_widget)
        right_splitter.addWidget(reg_group)

        stack_group = QGroupBox("Call Stack & Frame (EBP Relative)")
        stack_layout = QVBoxLayout(stack_group)
        self.stack_list = QListWidget()
        self.stack_list.setFont(QFont("Consolas", 10))
        self.stack_list.setStyleSheet("background-color: #252526;")
        stack_layout.addWidget(self.stack_list)
        right_splitter.addWidget(stack_group)

        mem_group = QGroupBox("Unified Memory (4KB) - Double Click to Edit")
        mem_layout = QVBoxLayout(mem_group)
        
        mem_ctrl_layout = QHBoxLayout()
        mem_ctrl_layout.addWidget(QLabel("View:"))
        self.mem_page_combo = QComboBox()
        self.mem_page_combo.addItems(["Data Segment (0x000)", "Stack Segment (0x800)", "Video Segment (0xF00)"])
        self.mem_page_combo.currentIndexChanged.connect(self.update_memory_view)
        mem_ctrl_layout.addWidget(self.mem_page_combo)
        
        mem_ctrl_layout.addWidget(QLabel("Size:"))
        self.mem_view_combo = QComboBox()
        self.mem_view_combo.addItems(["Bytes (8-bit)", "Words (16-bit)", "Dwords (32-bit)"])
        self.mem_view_combo.currentIndexChanged.connect(self.update_memory_view)
        mem_ctrl_layout.addWidget(self.mem_view_combo)
        mem_ctrl_layout.addStretch()
        mem_layout.addLayout(mem_ctrl_layout)
        
        self.mem_table = QTableWidget(16, 16)
        self.mem_table.setFont(QFont("Consolas", 10))
        self.mem_table.setStyleSheet("background-color: #252526; gridline-color: #333;")
        self.mem_table.horizontalHeader().setVisible(True)
        self.mem_table.verticalHeader().setVisible(True)
        self.mem_table.horizontalHeader().setDefaultSectionSize(60)
        self.mem_table.verticalHeader().setDefaultSectionSize(30)
        self.mem_table.setEditTriggers(QTableWidget.DoubleClicked)
        self.mem_table.itemChanged.connect(self.memory_edited)
        mem_layout.addWidget(self.mem_table)
        right_splitter.addWidget(mem_group)

        # VGA & Watch Splitter
        bottom_right_splitter = QSplitter(Qt.Horizontal)
        
        vga_group = QGroupBox("VGA Text Monitor (0xF00)")
        vga_layout = QVBoxLayout(vga_group)
        self.vga_screen = VGAScreen()
        vga_layout.addWidget(self.vga_screen, alignment=Qt.AlignCenter)
        bottom_right_splitter.addWidget(vga_group)

        watch_group = QGroupBox("Live Watch Window")
        watch_layout = QVBoxLayout(watch_group)
        self.watch_input = QLineEdit()
        self.watch_input.setPlaceholderText("Add watch (e.g. EAX, [EBP+8], msg) and press Enter")
        self.watch_input.setStyleSheet("background-color: #252526; padding: 4px;")
        self.watch_input.returnPressed.connect(self.add_watch)
        watch_layout.addWidget(self.watch_input)
        self.watch_list = QListWidget()
        self.watch_list.setFont(QFont("Consolas", 10))
        self.watch_list.setStyleSheet("background-color: #252526;")
        watch_layout.addWidget(self.watch_list)
        bottom_right_splitter.addWidget(watch_group)

        right_splitter.addWidget(bottom_right_splitter)

        splitter.addWidget(right_splitter)
        splitter.setSizes([600, 600])
        main_layout.addWidget(splitter, stretch=1)

        # --- CONSOLE ---
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 10))
        self.console.setStyleSheet("background-color: #1a1a1a; color: #569cd6;")
        self.console.setMaximumHeight(100)
        main_layout.addWidget(self.console)

        # --- CONTROLS ---
        controls_layout = QHBoxLayout()
        self.btn_load = QPushButton("⏳ Load")
        self.btn_reset = QPushButton("🔄 Reset")
        self.btn_back = QPushButton("⏮ Step Back")
        self.btn_step = QPushButton("⏭ Step Into")
        self.btn_over = QPushButton("⏭ Step Over")
        self.btn_out = QPushButton("⏭ Step Out")
        self.btn_run = QPushButton("▶ Run")
        
        for btn in [self.btn_load, self.btn_reset, self.btn_back, self.btn_step, self.btn_over, self.btn_out, self.btn_run]:
            btn.setFont(QFont("Segoe UI", 10))
            btn.setStyleSheet("background-color: #0e639c; color: white; padding: 8px; border-radius: 4px;")
            controls_layout.addWidget(btn)

        self.btn_back.setStyleSheet("background-color: #5a5a5a; color: white; padding: 8px; border-radius: 4px;")
        self.btn_over.setStyleSheet("background-color: #8a2be2; color: white; padding: 8px; border-radius: 4px;")
        self.btn_out.setStyleSheet("background-color: #d2691e; color: white; padding: 8px; border-radius: 4px;")
        
        controls_layout.addWidget(QLabel("Speed:"))
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(50, 1000)
        self.speed_slider.setValue(300)
        self.speed_slider.setInvertedAppearance(True)
        controls_layout.addWidget(self.speed_slider)
        main_layout.addLayout(controls_layout)

        self.btn_load.clicked.connect(self.load_code)
        self.btn_reset.clicked.connect(self.reset_cpu)
        self.btn_back.clicked.connect(self.step_back)
        self.btn_step.clicked.connect(self.step_into)
        self.btn_over.clicked.connect(self.step_over)
        self.btn_out.clicked.connect(self.step_out)
        self.btn_run.clicked.connect(self.toggle_run)
        self.speed_slider.valueChanged.connect(self.update_speed)

    def show_help(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Assembly Instruction Reference")
        dialog.resize(400, 600)
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(INSTRUCTION_REF)
        text_edit.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(text_edit)
        dialog.exec()

    def memory_edited(self, item):
        if self.is_updating_ui: return
        try:
            row = item.row()
            col = item.column()
            cols = self.mem_table.columnCount()
            item_idx = row * cols + col
            size = 2 ** self.mem_view_mode
            
            page_base = [0x000, 0x800, 0xF00][self.mem_page]
            addr = page_base + (item_idx * size)
            
            val = int(item.text(), 16)
            self.cpu._write_mem(addr, val, size)
            self.console.appendPlainText(f"> Memory[0x{addr:X}] manually set to 0x{val:X}")
        except ValueError:
            pass

    def add_watch(self):
        text = self.watch_input.text().strip()
        if text:
            self.watch_list.addItem(text)
            self.watch_input.clear()
            self.update_ui()

    def update_memory_view(self, idx=None):
        self.mem_page = self.mem_page_combo.currentIndex()
        self.mem_view_mode = self.mem_view_combo.currentIndex()
        size = 2 ** self.mem_view_mode
        cols = 16 // size
        self.mem_table.setColumnCount(cols)
        self.mem_table.setRowCount(16)
        
        for c in range(cols):
            self.mem_table.setHorizontalHeaderItem(c, QTableWidgetItem(f"+{c*size:02X}"))
        for r in range(16):
            self.mem_table.setVerticalHeaderItem(r, QTableWidgetItem(f"{r*16:02X}"))
            
        self.update_ui()

    def on_view_changed(self, index):
        self.view_mode = ["Hex", "Dec", "Bin"][index]
        self.update_ui()

    def on_mode_changed(self, index):
        bits = [16, 32, 64][index]
        self.cpu.set_mode(bits)
        code = """; Pinnacle Edition: VGA & REP Prefix
; 1. Setup Source String
msg DB 'H', 'E', 'L', 'L', 'O', 0

; 2. Setup Dest in Video Memory (0xF00)
MOV EDI, 0xF00
MOV ESI, msg
MOV ECX, 5
CLD

; 3. Hardware Accelerated Copy!
REP MOVSB

; 4. Exit
MOV EAX, 1
INT 0x80
"""
        self.code_editor.setPlainText(code)
        self.load_code()

    def load_code(self):
        self.cpu.load_code(self.code_editor.toPlainText())
        self.code_editor.exec_counts = self.cpu.exec_counts
        self.console.appendPlainText("> Code assembled. 4KB Memory initialized.")
        self.trace_list.clear()
        
        self.sym_list.clear()
        for typ, name, val in self.cpu.symbols:
            if typ == "Data":
                item = QListWidgetItem(f"[{typ}] {name}: 0x{val:02X}")
            elif typ == "Code":
                item = QListWidgetItem(f"[{typ}] {name}: Line {val}")
            else:
                item = QListWidgetItem(f"[{typ}] {name}: 0x{val:X}")
            self.sym_list.addItem(item)
            
        self.update_memory_view()
        self.update_ui()

    def reset_cpu(self):
        self.cpu.reset()
        self.code_editor.exec_counts = self.cpu.exec_counts
        self.console.appendPlainText("> CPU Reset.")
        self.timer.stop()
        self.btn_run.setText("▶ Run")
        self.is_running = False
        self.trace_list.clear()
        self.update_ui()

    def step_back(self):
        if self.cpu.restore_state():
            self.code_editor.exec_counts = self.cpu.exec_counts
            self.console.appendPlainText("> Stepped backwards (State Restored).")
            if self.trace_list.count() > 0:
                self.trace_list.takeItem(self.trace_list.count() - 1)
            self.update_ui()
        else:
            self.console.appendPlainText("> No history to step back to.")

    def step_into(self):
        self.step_over_target = None
        self.step_out_target = -1
        self.step_cpu()

    def step_over(self):
        if self.cpu.halted: return
        curr_instr = self.cpu.code[self.cpu.eip - 1]
        if "CALL" in curr_instr.upper() or "INT" in curr_instr.upper() or "REP" in curr_instr.upper():
            self.step_over_target = self.cpu.eip + 1
            if not self.is_running: self.toggle_run()
        else:
            self.step_cpu()

    def step_out(self):
        if self.cpu.halted: return
        self.step_out_target = self.cpu.registers[self.cpu.valid_regs[7]] 
        if not self.is_running: self.toggle_run()

    def run_to_line(self, line):
        if self.cpu.halted: return
        self.step_over_target = line
        if not self.is_running: self.toggle_run()

    def step_cpu(self):
        if self.cpu.halted:
            self.console.appendPlainText("> CPU is halted.")
            self.toggle_run()
            return
        
        info = self.cpu.step()
        
        if info["scan"]:
            if self.is_running: self.toggle_run() 
            val, ok = QInputDialog.getInt(self, "Sandbox I/O", f"Enter integer for instruction at Line {self.cpu.eip-1}:")
            if ok:
                self.cpu._set_value(self.cpu.code[self.cpu.eip - 1].split()[1], val)
                self.console.appendPlainText(f"> Input received: {val}")
            else:
                self.cpu.halted = True
                self.console.appendPlainText("> Input cancelled. CPU Halted.")
            self.update_ui()
            return

        self.console.appendPlainText(f"> {info['msg']}")
        if info["alu_trace"]:
            self.console.appendPlainText(f"   [{info['alu_trace']}]")
        if info["print"] is not None:
            self.console.appendPlainText(f"   [OUTPUT] >> {info['print']}")
        
        trace_item = QListWidgetItem(f"{self.cpu.instructions_executed}. L{info['line_num']}: {info['instr']}")
        self.trace_list.addItem(trace_item)
        self.trace_list.scrollToBottom()
        
        if info["flow"]:
            self.arch_viz.animate(info["flow"], info["decode"], info["cycles"])
            
        self.last_modified_reg = info["dest_reg"]
        self.update_ui()
        
        if self.last_modified_reg:
            self.flash_timer.start(600)
            
        bp_hit = self.cpu.eip in self.code_editor.breakpoints and not self.cpu.halted
        over_hit = self.cpu.eip == self.step_over_target
        out_hit = False
        
        if self.step_out_target != -1 and info["instr"].upper().startswith("RET"):
            curr_ebp = self.cpu.registers[self.cpu.valid_regs[7]]
            if curr_ebp <= self.step_out_target:
                out_hit = True
                self.step_out_target = -1
        
        if self.is_running and (bp_hit or over_hit or out_hit):
            self.toggle_run() 
            self.step_over_target = None
            if bp_hit: self.console.appendPlainText(f"> Breakpoint hit at line {self.cpu.eip}.")

    def clear_flash(self):
        self.last_modified_reg = None
        self.update_ui()

    def toggle_run(self):
        if self.is_running:
            self.timer.stop()
            self.is_running = False
            self.btn_run.setText("▶ Run")
        else:
            if self.cpu.halted: return
            self.timer.start(self.speed_slider.value())
            self.is_running = True
            self.btn_run.setText("⏸ Pause")

    def update_speed(self):
        if self.is_running:
            self.timer.setInterval(self.speed_slider.value())

    def format_val(self, val):
        if self.view_mode == "Hex":
            digits = {16: 4, 32: 8, 64: 16}[self.cpu.mode]
            return f"0x{val:0{digits}X}"
        elif self.view_mode == "Dec":
            return str(val)
        else:
            digits = {16: 16, 32: 32, 64: 64}[self.cpu.mode]
            return f"0b{val:0{digits}b}"

    def update_ui(self):
        self.is_updating_ui = True
        self.reg_list.clear()
        acc_reg = self.cpu.valid_regs[0] 
        sp_reg = self.cpu.valid_regs[6]
        bp_reg = self.cpu.valid_regs[7]
        
        for reg, val in self.cpu.registers.items():
            item = QListWidgetItem(f"{reg}: {self.format_val(val & self.cpu.mask)}")
            if reg == self.last_modified_reg:
                item.setBackground(QColor("#2d5a2d")) 
            self.reg_list.addItem(item)
        
        eip_item = QListWidgetItem(f"{self.cpu.ip_name}: Line 0x{self.cpu.eip:02X}")
        eip_item.setForeground(QColor("#f44747"))
        self.reg_list.addItem(eip_item)

        self.led_widget.set_value(self.cpu.registers[acc_reg], self.cpu.mode)
        self.flags_widget.set_flags(self.cpu.flags)

        # --- INTELLIGENT STACK FRAME VIEWER ---
        self.stack_list.clear()
        esp_val = self.cpu.registers[sp_reg]
        ebp_val = self.cpu.registers[bp_reg]
        ws = self.cpu.word_size
        
        for i in range(0x800, esp_val - ws, -ws):
            i = i - ws
            if i < 0: break
            val = self.cpu._read_mem(i, ws)
            label = ""
            color = QColor("#d4d4d4")
            
            if ebp_val != 0x800 and ebp_val != 0:
                if i == ebp_val:
                    label = "<-- [EBP] Saved Frame Pointer"
                    color = QColor("#4ec9b0") 
                elif i == ebp_val + ws:
                    label = "<-- [EBP+4] Return Address"
                    color = QColor("#f44747") 
                elif i > ebp_val + ws:
                    label = f"<-- [EBP+{i - ebp_val}] Argument"
                    color = QColor("#b5cea8") 
                elif i < ebp_val:
                    label = f"<-- [EBP-{ebp_val - i}] Local Variable"
                    color = QColor("#569cd6") 
                    
            if i == esp_val:
                label = (label + " & " if label else "") + "<-- [ESP] Top of Stack"
                color = QColor("#8a2be2") 
                
            item = QListWidgetItem(f"0x{i:03X}: 0x{val:0{ws*2}X}  {label}")
            item.setForeground(color)
            self.stack_list.addItem(item)

        # --- DYNAMIC MEMORY GRID ---
        size = 2 ** self.mem_view_mode
        cols = self.mem_table.columnCount()
        rows = self.mem_table.rowCount()
        page_base = [0x000, 0x800, 0xF00][self.mem_page]
        
        for r in range(rows):
            for c in range(cols):
                idx = r * cols + c
                addr = page_base + (idx * size)
                val = self.cpu._read_mem(addr, size)
                
                item = self.mem_table.item(r, c)
                if not item:
                    item = QTableWidgetItem()
                    self.mem_table.setItem(r, c, item)
                
                if self.mem_view_mode == 0: 
                    char = chr(val) if 32 <= val <= 126 else '.'
                    item.setText(f"{val:02X} ({char})")
                else:
                    item.setText(f"{val:0{size*2}X}")
                
                if page_base <= esp_val < page_base + 256 and addr <= esp_val < addr + size:
                    item.setBackground(QColor("#8a2be2")) 
                    item.setForeground(QColor("#ffffff"))
                elif page_base <= ebp_val < page_base + 256 and addr <= ebp_val < addr + size and ebp_val != 0x800:
                    item.setBackground(QColor("#007acc")) 
                    item.setForeground(QColor("#ffffff"))
                elif val != 0:
                    item.setBackground(QColor("#252526"))
                    item.setForeground(QColor("#4ec9b0")) 
                else:
                    item.setBackground(QColor("#252526"))
                    item.setForeground(QColor("#888888"))

        # --- VGA SCREEN ---
        self.vga_screen.update_mem(self.cpu.memory)

        # --- WATCH WINDOW ---
        for i in range(self.watch_list.count()):
            item = self.watch_list.item(i)
            expr = item.text().split('=')[0].strip()
            try:
                val, _ = self.cpu._get_value(expr, size=self.cpu.word_size)
                item.setText(f"{expr} = {self.format_val(val)}")
            except:
                item.setText(f"{expr} = <error>")

        self.code_editor.highlight_current_line(self.cpu.eip)
        self.code_editor.line_number_area.update()
        
        # --- STATS & PROFILE ---
        cpi = (self.cpu.total_cycles / self.cpu.instructions_executed) if self.cpu.instructions_executed > 0 else 0
        time_ns = (self.cpu.total_cycles / 3.0) # 3.0 GHz = 3 cycles per ns
        self.stats_label.setText(f"Cycles: {self.cpu.total_cycles} | Instr: {self.cpu.instructions_executed} | CPI: {cpi:.2f} | Time: {time_ns:.2f} ns")
        
        top_instrs = self.cpu.instr_profile.most_common(8)
        self.profile_chart.set_data(top_instrs)
        
        self.is_updating_ui = False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())