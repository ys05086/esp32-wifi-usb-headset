"""Outbound AAC comparison controls; changes apply on the next connection."""
import tkinter as tk
from tkinter import ttk, messagebox
from audio_quality import QualitySettings, SAMPLE_RATES, bitrates_for


def show_quality(parent, settings, active, apply):
    window = tk.Toplevel(parent)
    window.title('보내는 음질 · AAC 비교')
    window.transient(parent)
    window.resizable(False, False)
    window.configure(bg='#f5f1fa')
    pane = ttk.Frame(window, padding=24)
    pane.pack(fill='both', expand=True)
    ttk.Label(pane, text='보내는 목소리의 질감', font=('맑은 고딕',17,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,10))
    ttk.Label(pane, text='보내는 음성의 샘플레이트와 AAC 압축 음질을 조절해요.\n상대방에게서 돌아오는 소리는 변경하지 않아요.',wraplength=430).grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,16))
    modes={'원음 PCM · 추가 압축 없음':'pcm','AAC 압축·복원 · 실험':'aac'}
    mode=tk.StringVar(value=next(k for k,v in modes.items() if v==settings.mode))
    rate=tk.StringVar(value=str(settings.sample_rate))
    bitrate=tk.StringVar(value=str(settings.bitrate_kbps))
    widgets=[]
    for row,label,var,choices in [(2,'처리 방식',mode,list(modes)),(3,'샘플레이트 · Hz',rate,SAMPLE_RATES),(4,'AAC 비트레이트 · kbps',bitrate,bitrates_for(settings.sample_rate))]:
        ttk.Label(pane,text=label).grid(row=row,column=0,sticky='w',padx=(0,18),pady=5)
        box=ttk.Combobox(pane,textvariable=var,values=choices,state='readonly',width=28)
        box.grid(row=row,column=1,sticky='ew',pady=5);widgets.append(box)
    hint=tk.StringVar()
    def update(_=None):
        choices=bitrates_for(int(rate.get()))
        widgets[2]['values']=choices
        if int(bitrate.get()) not in choices: bitrate.set(str(choices[-1]))
        is_aac=modes[mode.get()]=='aac'
        widgets[0].configure(state='disabled' if active else 'readonly')
        for box in widgets[1:]:box.configure(state='readonly' if is_aac and not active else 'disabled')
        hint.set('AAC는 추가 지연이 생겨요. 낮은 샘플레이트일수록\n한 블록을 모으는 시간이 길어질 수 있어요.' if is_aac else '기존 PCM 경로로 전송해요. AAC 처리를 거치지 않아요.')
    for box in widgets:box.bind('<<ComboboxSelected>>',update)
    update()
    ttk.Label(pane,textvariable=hint,wraplength=430).grid(row=5,column=0,columnspan=2,sticky='w',pady=(14,8))
    ttk.Label(pane,text='선택한 형식으로 AAC 압축 → 복원 → 48 kHz PCM 전송\n보드 USB 형식과 Wi-Fi 전송량은 그대로예요.\n통화·메신저 앱 자체의 녹음·압축 설정을 바꾸는 기능은 아니에요.',wraplength=430,foreground='#766d82').grid(row=6,column=0,columnspan=2,sticky='w',pady=(0,14))
    if active:ttk.Label(pane,text='연결을 중지한 뒤 음질 설정을 바꿀 수 있어요.').grid(row=7,column=0,columnspan=2,sticky='w',pady=(0,10))
    def save():
        try: value=QualitySettings(modes[mode.get()],int(rate.get()),int(bitrate.get()));apply(value)
        except (ValueError,OSError) as error:messagebox.showerror('음질 설정',str(error),parent=window);return
        window.destroy()
    buttons=ttk.Frame(pane);buttons.grid(row=8,column=0,columnspan=2,sticky='e')
    ttk.Button(buttons,text='닫기',command=window.destroy).pack(side='left',padx=6)
    ttk.Button(buttons,text='저장 · 다음 연결에 적용',command=save,state='disabled' if active else 'normal').pack(side='left')
    window.grab_set()
