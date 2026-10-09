import json
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sounddevice as sd
from client import HeadsetClient
from protocol import slider_db, slider_position
from board_status import BoardStatus
from audio_quality import QualitySettings, quality_self_test
from quality_dialog import show_quality

CONFIG = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).parent / 'settings.json'


class App:
    def __init__(self, root):
        self.root, self.client = root, None
        root.title('ESP32 Audio Bridge'); root.geometry('700x760'); root.minsize(660, 740)
        root.configure(bg='#f5f1fa')
        style=ttk.Style(); style.theme_use('clam')
        style.configure('.',font=('맑은 고딕',10),background='#f5f1fa',foreground='#393247')
        style.configure('TButton',padding=10,background='#decdf2')
        style.configure('TEntry',padding=8); style.configure('TCombobox',padding=7)
        frame=ttk.Frame(root,padding=24); frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='ESP32 Audio Bridge',font=('맑은 고딕',23,'bold')).pack(anchor='w')
        ttk.Label(frame,text='USB로 꽂은 기기의 소리를 Wi-Fi로 PC에서 듣고, PC 마이크를 그 기기에',padding=(0,6,0,18)).pack(anchor='w')
        self.host=tk.StringVar(value='192.168.0.14')
        try: saved=json.loads(CONFIG.read_text(encoding='utf-8-sig')); self.host.set(saved.get('host',self.host.get()))
        except (OSError,ValueError): saved={}
        self.saved=saved
        self.quality=QualitySettings.restore(saved.get('quality'))
        self.quality_label=tk.StringVar(value=self.quality.label)
        ttk.Label(frame,text='ESP32 주소').pack(anchor='w')
        self.host_entry=ttk.Entry(frame,textvariable=self.host); self.host_entry.pack(fill='x',pady=(4,10))
        self.board=BoardStatus()
        self.usb_mode=tk.StringVar(value='USB 모드 · 확인 중…')
        ttk.Label(frame,textvariable=self.usb_mode,padding=(0,0,0,10)).pack(anchor='w')
        ttk.Label(frame,text='보낼 소리 · PC 마이크 / 오디오 입력').pack(anchor='w')
        self.input=ttk.Combobox(frame,state='readonly');self.input.pack(fill='x',pady=(4,10))
        ttk.Label(frame,text='기기 소리 · PC 이어폰 / 헤드폰').pack(anchor='w')
        self.output=ttk.Combobox(frame,state='readonly');self.output.pack(fill='x',pady=(4,10))
        row=ttk.Frame(frame);row.pack(fill='x',pady=(0,8))
        ttk.Label(row,text='듣기 버퍼 · 클수록 안정적, 지연 증가').pack(side='left')
        saved_buffer = saved.get('buffer_ms',80)
        self.buffer_ms=tk.StringVar(value=str(saved_buffer if saved_buffer in (40,80,120) else 80))
        self.buffer=ttk.Combobox(row,state='readonly',width=6,textvariable=self.buffer_ms,values=('40','80','120'))
        self.buffer.pack(side='left',padx=8);ttk.Label(row,text='ms').pack(side='left')
        self.mute=tk.BooleanVar(); self.deafen=tk.BooleanVar()
        row=ttk.Frame(frame);row.pack(fill='x',pady=5)
        ttk.Checkbutton(row,text='보낼 소리 음소거',variable=self.mute,command=self.controls).pack(side='left')
        ttk.Checkbutton(row,text='기기 소리 음소거',variable=self.deafen,command=self.controls).pack(side='right')
        self.volume=tk.DoubleVar(value=80)
        self.volume_label=tk.StringVar(value='듣기 크기');self.level_shown=None
        row=ttk.Frame(frame);row.pack(fill='x')
        ttk.Label(row,textvariable=self.volume_label).pack(side='left')
        ttk.Button(row,text='보내는 음질…',command=self.edit_quality).pack(side='right')
        ttk.Button(row,text='보드 설정…',command=self.open_setup).pack(side='right',padx=(0,8))
        ttk.Scale(frame,from_=0,to=100,variable=self.volume,command=lambda _:self.volume_moved()).pack(fill='x')
        row=ttk.Frame(frame);row.pack(fill='x',pady=12)
        self.button=ttk.Button(row,text='연결 시작',command=self.toggle);self.button.pack(side='left',expand=True,fill='x')
        self.refresh_button=ttk.Button(row,text='장치 새로고침',command=self.refresh);self.refresh_button.pack(side='left',padx=(10,0))
        ttk.Button(row,text='진단 저장',command=self.save_diagnostics).pack(side='left',padx=(8,0))
        self.status=tk.StringVar(value='ESP32의 USB 포트를 소리를 들을 기기에 연결하세요.')
        ttk.Label(frame,textvariable=self.status,wraplength=570).pack(anchor='w')
        self.stats=tk.StringVar();ttk.Label(frame,textvariable=self.stats,wraplength=570,padding=(0,8)).pack(anchor='w')
        ttk.Label(frame,textvariable=self.quality_label,foreground='#766d82',wraplength=610).pack(anchor='w')
        self.refresh();root.after(250,self.poll);root.protocol('WM_DELETE_WINDOW',self.close)

    def refresh(self):
        if self.client and self.client.active:return
        try:
            devices=sd.query_devices();apis=sd.query_hostapis()
            preferred=[i for i,d in enumerate(devices) if apis[d['hostapi']]['name']=='Windows WASAPI']
            # Some virtual cables expose only a legacy/KS endpoint. Keep them
            # selectable, with WASAPI first and the backend visible in the label.
            ids=preferred+[i for i in range(len(devices)) if i not in preferred]
            label=lambda i:f"{devices[i]['name']} · {apis[devices[i]['hostapi']]['name']} · {i}"
            self.inputs={label(i):i for i in ids if devices[i]['max_input_channels']}
            self.outputs={label(i):i for i in ids if devices[i]['max_output_channels']}
            for widget,values,key in [(self.input,self.inputs,'input'),(self.output,self.outputs,'output')]:
                widget['values']=list(values)
                old=self.saved.get(key,'');choice=next((name for name in values if name.rsplit(' · ',1)[0]==old),next(iter(values),''))
                widget.set(choice)
        except Exception as error:messagebox.showerror('오디오 장치',str(error))

    def controls(self):
        if self.client:
            self.client.mic_muted=self.mute.get();self.client.return_muted=self.deafen.get();self.client.output_gain=self.volume.get()/100

    def volume_moved(self):
        # Linked with the board: the slider sets the board's listening level (the phone's volume until then).
        self.controls()
        if self.client and self.client.active and self.client.listening.linked:
            self.client.listening.set(slider_db(self.volume.get()),time.monotonic())

    def show_level(self):
        level=self.client.listening if self.client else None
        if not (level and level.linked):
            self.volume_label.set('듣기 크기');self.level_shown=None;return
        # Follow the board (a phone volume change) unless our own change is still on its way.
        if not level.pending and level.changes!=self.level_shown:
            self.volume.set(slider_position(level.db));self.level_shown=level.changes
        where=' · PC에서 바꿈' if level.by_pc else (' · 폰 볼륨' if level.phone_sets else '')
        self.volume_label.set('듣기 크기 · 무음'+where if level.db is None else f'듣기 크기 · {level.db:.1f} dB'+where)

    def edit_quality(self):
        def apply(value):
            saved={**self.saved,'quality':value.to_dict()}
            CONFIG.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
            self.saved=saved;self.quality=value;self.quality_label.set(value.label)
        show_quality(self.root,self.quality,bool(self.client and self.client.active),apply)

    def open_setup(self):
        # Board Wi-Fi, router, USB mode and firmware installs: a program of its own, over the COM port.
        if getattr(sys,'frozen',False):command=[str(Path(sys.executable).with_name('ESP32BoardSetup.exe'))]
        else:command=[sys.executable,str(Path(__file__).with_name('board_setup.py'))]
        try:subprocess.Popen(command)
        except OSError as error:messagebox.showerror('보드 설정',str(error))

    def toggle(self):
        if self.client and self.client.active:self.client.stop();return
        try:
            client=HeadsetClient(self.host.get().strip(),self.inputs[self.input.get()],self.outputs[self.output.get()],int(self.buffer_ms.get()),self.quality)
            self.client=client;self.controls();client.start()
            self.saved={'host':self.host.get().strip(),'input':self.input.get().rsplit(' · ',1)[0],'output':self.output.get().rsplit(' · ',1)[0],'buffer_ms':int(self.buffer_ms.get()),'quality':self.quality.to_dict()}
            try:CONFIG.write_text(json.dumps(self.saved,ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError:pass
        except Exception as error:messagebox.showerror('연결',str(error))

    def save_diagnostics(self):
        if not self.client:
            messagebox.showinfo('진단 저장','연결을 한 번 시작한 뒤 저장해 주세요.');return
        path=filedialog.asksaveasfilename(defaultextension='.json',initialfile='esp32-audio-diagnostics.json',filetypes=[('JSON','*.json')])
        if not path:return
        c=self.client;b=c.returns
        report={'input':self.input.get(),'output':self.output.get(),'status':c.status,
                'input_rate':c.input_rate,'output_rate':c.output_rate,'target_buffer_ms':b.target_blocks*10,
                'return_received':b.received,'return_lost_at_playback':b.lost,'return_underruns':b.underruns,
                'return_late':b.late,'return_reordered':b.reordered,'return_discarded':b.discarded,
                'queued_ms':b.queued_ms,'max_return_arrival_gap_ms':round(b.max_gap_ms,2),
                'capture_device_errors':c.capture_errors,'playback_device_errors':c.playback_errors,
                'sent':c.sent,'board_received':c.board_received,'board_mic_underruns':c.board_underruns,
                'board_return_drops':c.board_return_drops,'capture_queue_drops':c.input_drops,
                'listen_rate_ppm':round(c.level.rate_ppm),'listen_frames_removed':c.level.removed,
                'listen_frames_added':c.level.added,'listen_step':c.level.adjust,
                'outbound_quality':c.quality.to_dict(),'aac_processing':c.quality_report,
                'aac_queue_drops':c.quality_drops,'send_queue_underruns':c.send_underruns,
                'listening_level':{'linked':c.listening.linked,'db':c.listening.db,'set_by_pc':c.listening.by_pc,
                                   'phone_sets_volume':c.listening.phone_sets},
                'board_status':self.board.report()}
        try:Path(path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError as error:messagebox.showerror('진단 저장',str(error))

    def poll(self):
        self.board.poll(self.host.get())
        self.usb_mode.set(self.board.label)
        active=self.client is not None and self.client.active
        self.button.configure(text='연결 중지' if active else '연결 시작')
        self.host_entry.configure(state='disabled' if active else 'normal')
        self.buffer.configure(state='disabled' if active else 'readonly')
        for widget in [self.input,self.output]:widget.configure(state='disabled' if active else 'readonly')
        self.refresh_button.configure(state='disabled' if active else 'normal')
        self.show_level()
        if self.client:
            c=self.client;self.status.set(c.status)
            if active and c.quality.mode=='aac':
                wait=c.quality_report.get('pending_ms',0)+c.outbound.qsize()*10+c.captured.qsize()*10
                self.quality_label.set(f'{c.quality.label} · AAC/송신 대기 약 {wait:.0f} ms\n추가 대기 추정치이며 전체 지연은 아니에요. · 송신 부족 {c.send_underruns} · AAC 버림 {c.quality_drops}')
            else:self.quality_label.set(self.quality.label)
            self.stats.set(f'입력 {c.input_rate} Hz → 전송 48000 Hz → 출력 {c.output_rate} Hz\n송신: 보냄 {c.sent} · 보드 수신 {c.board_received} · 보드 버퍼 부족 {c.board_underruns}\n듣기: 수신 {c.returns.received} · 버퍼 {c.returns.queued_ms} ms · 누락 {c.returns.lost}\n듣기 버퍼 부족 {c.returns.underruns} · 출력 장치 오류 {c.playback_errors} · 입력 버림 {c.input_drops}\n듣기 속도 보정 {c.level.rate_ppm:+.0f} ppm (−{c.level.removed}/+{c.level.added} 프레임)')
        self.root.after(250,self.poll)

    def close(self):
        if self.client:self.client.stop()
        self.root.destroy()


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--quality-self-test':
        report=quality_self_test()
        Path(sys.argv[2]).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        sys.exit(0 if report['ok'] else 1)
    root=tk.Tk()
    if len(sys.argv)==3 and sys.argv[1] in ('--self-test', '--audio-self-test', '--aac-audio-self-test'):
        root.withdraw(); application=App(root); root.update_idletasks()
        if sys.argv[1] in ('--audio-self-test', '--aac-audio-self-test'):
            from audio_diagnostics import audio_self_test
            quality=QualitySettings('aac') if sys.argv[1]=='--aac-audio-self-test' else None
            report = audio_self_test(application.inputs[application.input.get()], application.outputs[application.output.get()],quality)
        else:
            report = {'inputs':len(application.inputs),'outputs':len(application.outputs),'ok':True,
                      'requested_height':root.winfo_reqheight(),'quality':application.quality.to_dict()}
        Path(sys.argv[2]).write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
        root.destroy()
    else:
        App(root);root.mainloop()
