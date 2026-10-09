"""ESP32 보드 설정: the board's own Wi-Fi, its router and USB mode over the COM port, and firmware installs.

Everything goes through the COM (USB-serial) port: plugging it in is the permission. Each action opens the
port, does its work and closes it again, so a serial monitor can still use the port in between.
"""
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import board_link
import firmware_bundle

MODES = {'standard': 'Standard · Windows 호환', 'apple': 'Apple · 아이폰 호환 (시험한 갤럭시도)',
         'adaptive': 'Adaptive · 피드백 없음 (실험)'}
INSTALL_BAUD = 460800


class SetupWindow:
    def __init__(self, root, probe=True):
        self.root = root
        self.results = queue.Queue()
        self.busy = False
        self.state = None
        self.ports = {}
        root.title('ESP32 보드 설정')
        root.geometry('660x760')
        root.minsize(620, 740)
        root.configure(bg='#f5f1fa')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('맑은 고딕', 10), background='#f5f1fa', foreground='#393247')
        style.configure('TButton', padding=5, background='#decdf2')
        style.configure('TEntry', padding=4)
        style.configure('TCombobox', padding=4)
        style.configure('TLabelframe', background='#f5f1fa')
        style.configure('TLabelframe.Label', font=('맑은 고딕', 11, 'bold'))
        style.configure('Hint.TLabel', foreground='#766d82')
        frame = ttk.Frame(root, padding=(22, 14))
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='ESP32 보드 설정', font=('맑은 고딕', 18, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='보드의 COM 포트(USB-시리얼)를 이 PC에 연결하세요. 처음 설정과 펌웨어 설치를 여기서 해요.',
                  style='Hint.TLabel', wraplength=600, padding=(0, 2, 0, 8)).pack(anchor='w')

        row = ttk.Frame(frame); row.pack(fill='x')
        ttk.Label(row, text='포트').pack(side='left')
        self.port = ttk.Combobox(row, state='readonly', width=34)
        self.port.pack(side='left', padx=8)
        self.port.bind('<<ComboboxSelected>>', lambda _: self.read())
        ttk.Button(row, text='다시 찾기', command=self.find_ports).pack(side='left')
        ttk.Button(row, text='읽기', command=self.read).pack(side='left', padx=(6, 0))
        self.status = tk.StringVar(value='')
        ttk.Label(frame, textvariable=self.status, wraplength=610, padding=(0, 6)).pack(anchor='w')

        box = ttk.LabelFrame(frame, text='보드 자체 Wi-Fi', padding=(10, 6)); box.pack(fill='x', pady=(0, 6))
        self.ap_ssid, self.ap_password = tk.StringVar(), tk.StringVar()
        self.field(box, 0, '이름', self.ap_ssid)
        self.field(box, 1, '비밀번호', self.ap_password, editable=True)
        buttons = ttk.Frame(box); buttons.grid(row=1, column=2, sticky='e')
        self.copy_button = ttk.Button(buttons, text='복사', command=self.copy_password)
        self.copy_button.pack(side='left')
        self.ap_button = ttk.Button(buttons, text='저장', command=self.save_ap_password)
        self.ap_button.pack(side='left', padx=(6, 0))
        self.new_button = ttk.Button(buttons, text='무작위', command=self.new_password)
        self.new_button.pack(side='left', padx=(6, 0))
        ttk.Label(box, text='비밀번호는 고쳐서 저장하거나 무작위로 만들 수 있어요 (8~63자, 영문·숫자·기호). '
                  '공유기 없이 휴대폰을 이 Wi-Fi에 바로 연결하면 보드 주소는 192.168.4.1이에요.',
                  style='Hint.TLabel', wraplength=590).grid(row=2, column=0, columnspan=3, sticky='w', pady=(6, 0))
        box.columnconfigure(1, weight=1)

        box = ttk.LabelFrame(frame, text='공유기 Wi-Fi (2.4 GHz)', padding=(10, 6)); box.pack(fill='x', pady=(0, 6))
        self.wifi_ssid, self.wifi_password = tk.StringVar(), tk.StringVar()
        ttk.Label(box, text='이름').grid(row=0, column=0, sticky='w')
        ttk.Entry(box, textvariable=self.wifi_ssid).grid(row=0, column=1, sticky='ew', padx=8, pady=3)
        ttk.Label(box, text='비밀번호').grid(row=1, column=0, sticky='w')
        ttk.Entry(box, textvariable=self.wifi_password, show='•').grid(row=1, column=1, sticky='ew', padx=8, pady=3)
        buttons = ttk.Frame(box); buttons.grid(row=0, column=2, rowspan=2)
        self.wifi_button = ttk.Button(buttons, text='저장', command=self.save_wifi)
        self.wifi_button.pack(fill='x')
        self.forget_button = ttk.Button(buttons, text='지우기', command=self.forget_wifi)
        self.forget_button.pack(fill='x', pady=(4, 0))
        self.router = tk.StringVar()
        ttk.Label(box, textvariable=self.router, wraplength=590).grid(row=2, column=0, columnspan=3, sticky='w', pady=(6, 0))
        box.columnconfigure(1, weight=1)

        box = ttk.LabelFrame(frame, text='USB 모드', padding=(10, 6)); box.pack(fill='x', pady=(0, 6))
        self.mode = ttk.Combobox(box, state='readonly', values=list(MODES.values()))
        self.mode.grid(row=0, column=0, sticky='ew')
        self.mode_button = ttk.Button(box, text='저장', command=self.save_mode)
        self.mode_button.grid(row=0, column=1, padx=(8, 0))
        self.mode_note = tk.StringVar()
        ttk.Label(box, textvariable=self.mode_note, style='Hint.TLabel', wraplength=590).grid(
            row=1, column=0, columnspan=2, sticky='w', pady=(6, 0))
        box.columnconfigure(0, weight=1)

        box = ttk.LabelFrame(frame, text='펌웨어', padding=(10, 6)); box.pack(fill='x')
        self.versions = tk.StringVar()
        ttk.Label(box, textvariable=self.versions, wraplength=590).grid(row=0, column=0, columnspan=3, sticky='w')
        self.reset_settings = tk.BooleanVar()
        ttk.Checkbutton(box, text='설정도 초기화 (새 보드 비밀번호, 공유기·USB 모드 지움)',
                        variable=self.reset_settings).grid(row=1, column=0, sticky='w', pady=6)
        self.folder_button = ttk.Button(box, text='폴더 고르기…', command=self.pick_folder)
        self.folder_button.grid(row=1, column=1, padx=6)
        self.install_button = ttk.Button(box, text='펌웨어 설치', command=self.install)
        self.install_button.grid(row=1, column=2)
        self.progress = ttk.Progressbar(box, maximum=1.0)
        self.progress.grid(row=2, column=0, columnspan=3, sticky='ew')
        self.progress_text = tk.StringVar()
        ttk.Label(box, textvariable=self.progress_text, style='Hint.TLabel', wraplength=590).grid(
            row=3, column=0, columnspan=3, sticky='w', pady=(4, 0))
        box.columnconfigure(0, weight=1)

        self.bundle = self.bundle_error = None
        try:
            self.bundle = firmware_bundle.load()
        except FileNotFoundError:
            self.bundle_error = '이 프로그램 옆에 firmware 폴더가 없어요. 받은 펌웨어 폴더를 고르세요.'
        except (OSError, ValueError, KeyError) as error:
            self.bundle_error = str(error)
        self.show()
        if probe:
            self.find_ports()
        root.after(100, self.poll)

    def field(self, box, row, label, variable, editable=False):
        ttk.Label(box, text=label).grid(row=row, column=0, sticky='w')
        ttk.Entry(box, textvariable=variable, state='normal' if editable else 'readonly', font=('Consolas', 11)).grid(
            row=row, column=1, sticky='ew', padx=8, pady=3)

    # --- background work: one job at a time, results back on the Tk thread

    def run(self, describe, task, done):
        if self.busy:
            return
        name = self.ports.get(self.port.get())
        if not name:
            self.status.set('COM 포트를 고르세요. 안 보이면 케이블과 USB-시리얼 드라이버를 확인하세요.')
            return
        self.busy = True
        self.status.set(describe)
        self.show()

        def work():
            try:
                result, error = task(name), None
            except Exception as exc:   # shown in the window
                result, error = None, exc
            self.results.put((done, result, error))
        threading.Thread(target=work, name='board-setup', daemon=True).start()

    def poll(self):
        while True:
            try:
                item = self.results.get_nowait()
            except queue.Empty:
                break
            if item[0] == 'progress':
                self.progress['value'], text = item[1]
                self.progress_text.set(text)
                continue
            done, result, error = item
            self.busy = False
            done(result, error)
            self.show()
        self.root.after(100, self.poll)

    @staticmethod
    def with_link(action):
        def task(name):
            port = board_link.open_port(name)
            try:
                return action(board_link.BoardLink(port))
            finally:
                port.close()
        return task

    # --- actions

    def find_ports(self):
        try:
            found = board_link.list_ports()
        except Exception as error:
            self.status.set(f'포트 목록을 못 읽었어요: {error}')
            return
        self.ports = {label: device for device, label, _ in found}
        known = {label for _, label, chip in found if chip}
        self.port['values'] = list(self.ports)
        if self.port.get() not in self.ports:
            self.port.set(next(iter(self.ports), ''))
        if not found:
            self.status.set('COM 포트가 없어요. 보드의 COM 쪽 단자를 데이터 케이블로 연결하세요.')
        elif self.port.get() in known:
            self.read()
        else:   # an unknown serial device: send it nothing until asked
            self.status.set('보드용 USB-시리얼 칩이 안 보여요. 보드의 COM 단자를 연결하고 다시 찾기를 누르거나, 포트를 골라 읽기를 누르세요.')

    def read(self, quiet=False):
        def done(state, error):
            if error:
                self.state = None
                self.status.set(f'{self.port.get()}: 보드가 답하지 않아요. 이 펌웨어가 아직 없거나, 다른 프로그램이 포트를 쓰고 있어요.'
                                ' 아래에서 펌웨어를 설치할 수 있어요.' if not quiet else f'다시 읽지 못했어요: {error}')
            else:
                self.apply(state)
        self.run('보드를 읽는 중…', self.with_link(lambda link: link.get()), done)

    def apply(self, state, message=None):
        self.state = state
        self.ap_ssid.set(state.get('ap_ssid', ''))
        self.ap_password.set(state.get('ap_password', ''))
        self.wifi_ssid.set(state.get('wifi_ssid', ''))
        self.wifi_password.set('')
        mode = state.get('usb_mode_saved', state.get('usb_mode'))
        self.mode.set(MODES.get(mode, ''))
        self.status.set(message or f"{self.port.get()} · 펌웨어 {state.get('firmware', '?')} · 읽기 완료")

    def show(self):
        s = self.state
        if s and s.get('wifi_ssid'):
            self.router.set(f"연결됨 · 보드 주소 {s['router_ip']}  ← PC 앱과 휴대폰 앱에 이 주소를 넣으세요" if s.get('wifi_connected')
                            else f"'{s['wifi_ssid']}'에 연결 중이거나 연결 실패 · 이름과 비밀번호를 확인하세요")
        elif s:
            self.router.set('저장된 공유기가 없어요. 휴대폰을 보드 Wi-Fi에 바로 연결해 쓸 수도 있어요.')
        else:
            self.router.set('')
        if s and s.get('usb_mode') != s.get('usb_mode_saved'):
            self.mode_note.set(f"지금은 {MODES.get(s.get('usb_mode'), '?').split(' ·')[0]} · 보드의 USB와 COM 케이블을 "
                               '모두 뺐다 꽂으면 저장한 모드로 바뀌어요.')
        else:
            self.mode_note.set('소리가 한쪽만 나거나 안 나면 바꿔 보세요. 저장한 뒤 보드의 USB와 COM 케이블을 모두 뺐다 꽂으면 적용돼요.')
        board = s.get('firmware', '?') if s else '확인 안 됨'
        if self.bundle:
            where = '이 프로그램에 든 것' if self.bundle.folder == firmware_bundle.default_folder() else self.bundle.folder.name
            self.versions.set(f'설치할 펌웨어: {self.bundle.version} ({where}) · 지금 보드: {board}')
        else:
            self.versions.set(f'설치할 펌웨어: 없음 · {self.bundle_error} · 지금 보드: {board}')
        ready = not self.busy and bool(s)
        for button in (self.copy_button, self.ap_button, self.new_button, self.wifi_button, self.forget_button,
                       self.mode_button):
            button.configure(state='normal' if ready else 'disabled')
        self.install_button.configure(state='normal' if not self.busy and self.bundle else 'disabled')
        self.folder_button.configure(state='disabled' if self.busy else 'normal')

    def copy_password(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.ap_password.get())
        self.status.set('보드 Wi-Fi 비밀번호를 복사했어요.')

    def changed(self, message):
        def done(state, error):
            if error:
                self.status.set(f'저장하지 못했어요: {error}')
            else:
                self.apply(state, message)
        return done

    def save_ap_password(self):
        password = self.ap_password.get()
        problem = board_link.ap_password_problem(password)
        if problem:
            self.status.set(f'보드 Wi-Fi 비밀번호: {problem}')
            return
        if self.state and password == self.state.get('ap_password'):
            self.status.set('보드 Wi-Fi 비밀번호가 그대로예요. 칸에서 고친 뒤 저장하세요.')
            return
        text = f'보드 Wi-Fi 비밀번호를 "{password}"로 바꿀까요?\n보드 Wi-Fi에 바로 연결해 쓰던 휴대폰과 PC는 새 비밀번호로 다시 연결해야 해요.'
        if len(password) < 10:
            text += '\n\n10자보다 짧으면 근처에서 추측하기 쉬워요.'
        if not messagebox.askyesno('보드 Wi-Fi 비밀번호', text, parent=self.root):
            return
        self.run('비밀번호를 저장하는 중…', self.with_link(lambda link: link.set(ap_password=password)),
                 self.changed('비밀번호를 저장했어요. 보드 Wi-Fi에 연결했던 기기는 새 비밀번호로 다시 연결하세요.'))

    def new_password(self):
        if not messagebox.askyesno('무작위 비밀번호', '보드 Wi-Fi 비밀번호를 무작위로 새로 만들까요?\n보드 Wi-Fi에 바로 연결해 쓰던 휴대폰과 PC는 '
                                   '새 비밀번호로 다시 연결해야 해요.', parent=self.root):
            return
        self.run('새 비밀번호를 만드는 중…', self.with_link(lambda link: link.new_password()),
                 self.changed('새 비밀번호를 저장했어요. 보드 Wi-Fi에 연결했던 기기는 다시 연결하세요.'))

    def save_wifi(self):
        ssid, password = self.wifi_ssid.get().strip(), self.wifi_password.get()
        if not ssid:
            self.status.set('공유기 이름을 넣으세요.'); return
        if len(ssid.encode()) > 32:
            self.status.set('공유기 이름이 너무 길어요 (32바이트까지).'); return
        if password and not 8 <= len(password) <= 63:
            self.status.set('공유기 비밀번호는 8~63자예요.'); return
        if not password and not messagebox.askyesno('공유기 Wi-Fi', f"'{ssid}'는 비밀번호 없는 Wi-Fi인가요?", parent=self.root):
            self.status.set('공유기 비밀번호를 넣고 저장하세요. 보드는 저장된 비밀번호를 보여 주지 않아서 바꿀 때마다 넣어야 해요.')
            return

        def done(state, error):
            self.changed(f"'{ssid}'를 저장했어요. 연결되면 보드 주소가 나타나요.")(state, error)
            if not error:
                self.root.after(6000, lambda: self.read(quiet=True))   # the address appears once it has joined
        self.run('공유기 설정을 저장하는 중…', self.with_link(lambda link: link.set(wifi_ssid=ssid, wifi_password=password)), done)

    def forget_wifi(self):
        if not messagebox.askyesno('공유기 Wi-Fi', '저장된 공유기를 지울까요? 그다음엔 보드 Wi-Fi에 바로 연결해서 써야 해요.',
                                   parent=self.root):
            return
        self.run('공유기 설정을 지우는 중…', self.with_link(lambda link: link.set(wifi_ssid='')),
                 self.changed('공유기 설정을 지웠어요.'))

    def save_mode(self):
        mode = next((key for key, label in MODES.items() if label == self.mode.get()), None)
        if not mode:
            return
        self.run('USB 모드를 저장하는 중…', self.with_link(lambda link: link.set(usb_mode=mode)),
                 self.changed('USB 모드를 저장했어요. 보드의 USB와 COM 케이블을 모두 뺐다 꽂으면 적용돼요.'))

    def pick_folder(self):
        folder = filedialog.askdirectory(title='펌웨어 폴더 (manifest.json이 있는 곳)', parent=self.root)
        if not folder:
            return
        try:
            self.bundle, self.bundle_error = firmware_bundle.load(folder), None
        except (OSError, ValueError, KeyError) as error:
            self.bundle, self.bundle_error = None, f'{folder}: {error}'
        self.show()

    def install(self):
        if not self.bundle:
            return
        name = self.ports.get(self.port.get(), '')
        if 'ESP32-S3' in self.port.get():
            self.status.set('이 포트는 보드의 오디오 USB 쪽이에요. COM(USB-시리얼) 단자를 연결해서 고르세요.')
            return
        wipe = self.reset_settings.get()
        text = (f'{name} 보드에 펌웨어 {self.bundle.version}를 설치할까요?\n\n설치하는 1분쯤 동안 소리가 끊기고, 끝나면 보드가 '
                '다시 시작해요. 그동안 케이블을 빼지 마세요.')
        if wipe:
            text += '\n\n설정도 지워요: 보드 Wi-Fi 비밀번호가 새로 만들어지고 공유기 설정과 USB 모드가 없어져요.'
        if not messagebox.askyesno('펌웨어 설치', text, parent=self.root):
            return
        bundle = self.bundle

        def task(port_name):
            port = board_link.open_port(port_name)
            try:
                firmware_bundle.install(port, bundle, wipe, baud=INSTALL_BAUD,
                                        progress=lambda f, t: self.results.put(('progress', (f, t))))
            finally:
                port.close()
            # The new firmware boots in a second or two; ask it until it answers.
            deadline = time.monotonic() + 12
            while True:
                time.sleep(1.5)
                try:
                    return self.with_link(lambda link: link.get())(port_name)
                except Exception:
                    if time.monotonic() > deadline:
                        return None

        def done(state, error):
            if error:
                self.progress_text.set('')
                self.status.set(f'설치하지 못했어요: {error}\n다시 해 보고, 그래도 안 되면 BOOT를 누른 채 RESET을 눌렀다 떼고 '
                                '다시 설치를 누르세요.')
            elif state:
                self.apply(state, f"설치 끝 · 펌웨어 {state.get('firmware', '?')}가 돌고 있어요.")
            else:
                self.state = None
                self.status.set('설치는 확인까지 끝났는데 보드가 아직 답하지 않아요. RESET 버튼을 누르거나 케이블을 다시 꽂고 읽기를 누르세요.')
        self.progress['value'] = 0
        self.run('펌웨어를 설치하는 중…', task, done)


def main():
    root = tk.Tk()
    SetupWindow(root)
    root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        import json
        from pathlib import Path
        root = tk.Tk(); root.withdraw()
        window = SetupWindow(root, probe=False); root.update_idletasks()
        report = {'ok': True, 'requested_height': root.winfo_reqheight(), 'bundle': bool(window.bundle),
                  'bundle_version': window.bundle.version if window.bundle else None, 'bundle_error': window.bundle_error}
        Path(sys.argv[2]).write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        root.destroy()
    else:
        main()
