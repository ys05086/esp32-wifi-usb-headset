#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "lwip/sockets.h"
#include "cJSON.h"
#include "wifi_bridge.h"
#include "wifi_pcm.h"
#include "usb_profile.h"
#include "usb_diagnostics.h"
#include "usb_mic_trace.h"
#include "board_config.h"
#include <stdlib.h>

static const char *TAG = "wifi_pcm";
static wifi_pcm_t pcm;
static portMUX_TYPE pcm_lock = portMUX_INITIALIZER_UNLOCKED;
static esp_netif_t *station, *access_point;
static bool configured;
typedef struct {
    uint32_t session, generation;
    int64_t created_ms;
    uint8_t data[960];
} return_audio_t;
static QueueHandle_t return_queue;
static struct sockaddr_in owner;
static bool owner_valid, duplex;
static uint32_t generation, return_sent, return_dropped;
// Device sound lost on the board without a count before: frames of half-built blocks thrown away (a 50 ms
// stall or a new session), and finished blocks not sent: too old (over 80 ms) or no longer for this phone.
static uint32_t return_partial_frames, return_stale, return_invalid;
static const char page[] =
"<!doctype html><html><meta name='viewport' content='width=device-width,initial-scale=1'><meta charset='utf-8'>"
"<title>ESP32 Wi-Fi Headset</title><style>body{background:#f5f1fa;color:#343044;font:16px system-ui;max-width:440px;margin:40px auto;padding:22px}"
"input,button{box-sizing:border-box;width:100%;padding:14px;margin:8px 0;border:1px solid #ddd;border-radius:14px}button{background:#d9c9ee}pre{white-space:pre-wrap}</style>"
"<h1>ESP32 Wi-Fi Headset</h1><p>Wi-Fi ↔ USB audio bridge</p>"
"<p>Connect this board and your phone to the same 2.4 GHz Wi-Fi. Leave this page open to see the board IP.</p>"
"<p>Settings save only while you are on this board's own Wi-Fi (its password is in the setup program); from the router side this page shows status only.</p>"
"<form id=f><input id=s placeholder='Wi-Fi name (SSID)' maxlength=32 required><input id=p type=password placeholder='Wi-Fi password' maxlength=63>"
"<button>Save Wi-Fi</button></form><pre id=r>Loading…</pre><p>Direct mode: 192.168.4.1 · UDP 49152</p>"
"<h2>USB compatibility</h2><p>These are audio compatibility profiles, not OS detection. Android may work with either profile; keep the one that works on your phone.</p>"
"<select id=u><option value=standard>Standard (Windows-compatible)</option><option value=apple>Apple-compatible (also works on tested Galaxy)</option><option value=adaptive>Adaptive (experimental, no feedback)</option></select>"
"<button onclick=\"fetch('/usb-mode',{method:'POST',body:u.value}).then(x=>x.text()).then(x=>alert(x))\">Save USB mode</button>"
"<script>f.onsubmit=async e=>{e.preventDefault();try{r.textContent=await(await fetch('/wifi',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ssid:s.value,password:p.value})})).text();p.value=''}catch(e){r.textContent=String(e)}};"
"setInterval(async()=>{try{r.textContent=JSON.stringify(await(await fetch('/status')).json(),null,2)}catch(e){}},2000)</script></html>";

void wifi_bridge_read(uint8_t *out, size_t bytes) {
    // Only the UAC microphone task calls this. The copy runs under the lock, the interpolation outside it.
    static int16_t raw[PCM_PACKET_FRAMES + 2];
    for (size_t done = 0, total = bytes/2; done < total; ) {
        size_t frames = total - done < PCM_PACKET_FRAMES ? total - done : PCM_PACKET_FRAMES;
        portENTER_CRITICAL(&pcm_lock);
        size_t taken = wifi_pcm_take(&pcm, raw, frames, esp_timer_get_time()/1000);
        vs_mic_trace_source(pcm.count);
        portEXIT_CRITICAL(&pcm_lock);
        wifi_pcm_render(raw, taken, out + done*2, frames);
        done += frames;
    }
    if (bytes & 1) out[bytes-1] = 0;
}
void wifi_bridge_speaker(const uint8_t *stereo, size_t bytes) {
    // Only the UAC speaker task owns this assembler. Never call sockets from it.
    static return_audio_t block;
    static size_t frames;
    if (!return_queue) return;
    int64_t now = esp_timer_get_time()/1000;
    portENTER_CRITICAL(&pcm_lock);
    bool enabled = duplex && owner_valid && pcm.active && now-pcm.last_ms <= 300;
    uint32_t session = pcm.session, epoch = generation;
    portEXIT_CRITICAL(&pcm_lock);
    if (!enabled) { frames = 0; return; }
    if (block.generation != epoch || (frames && now-block.created_ms > 50)) {
        if (frames) { portENTER_CRITICAL(&pcm_lock); return_partial_frames += frames; portEXIT_CRITICAL(&pcm_lock); }
        frames = 0;
    }
    block.session = session; block.generation = epoch;
    for (size_t i=0; i+3<bytes; i+=4) {
        if (!frames) block.created_ms = now;
        int32_t left=(int16_t)(stereo[i] | (unsigned)stereo[i+1]<<8);
        int32_t right=(int16_t)(stereo[i+2] | (unsigned)stereo[i+3]<<8);
        uint16_t sample=(uint16_t)(int16_t)((left+right)/2);
        block.data[frames*2]=(uint8_t)sample; block.data[frames*2+1]=(uint8_t)(sample>>8);
        if (++frames==480) {
            if (xQueueSend(return_queue,&block,0)!=pdTRUE) {
                return_audio_t old;
                xQueueReceive(return_queue,&old,0);
                xQueueSend(return_queue,&block,0);
                portENTER_CRITICAL(&pcm_lock); return_dropped++; portEXIT_CRITICAL(&pcm_lock);
            }
            frames=0;
        }
    }
}

static void udp_task(void *arg) {
    (void)arg;
    int fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    struct sockaddr_in address = {.sin_family=AF_INET,.sin_port=htons(49152),.sin_addr.s_addr=htonl(INADDR_ANY)};
    if (fd < 0 || bind(fd,(struct sockaddr*)&address,sizeof address) != 0) {
        ESP_LOGE(TAG,"UDP bind failed: %d",errno); if(fd>=0)close(fd); vTaskDelete(NULL); return;
    }
    struct timeval timeout={.tv_sec=0,.tv_usec=2000};
    setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof timeout);
    // One UDP task owns these buffers; keep ~3 KB off its lwIP call stack.
    static uint8_t packet[PCM_PACKET_BYTES+1];
    static return_audio_t block;
    static uint8_t back[PCM_PACKET_BYTES];
    uint32_t return_sequence=0;
    while(1) {
        struct sockaddr_in peer; socklen_t peer_len=sizeof peer;
        int n=recvfrom(fd,packet,sizeof packet,0,(struct sockaddr*)&peer,&peer_len);
        if(n>=0) {
            uint32_t reply[6]; bool accepted, full;
            int64_t now=esp_timer_get_time()/1000;
            portENTER_CRITICAL(&pcm_lock);
            bool same_peer=owner_valid && owner.sin_addr.s_addr==peer.sin_addr.s_addr && owner.sin_port==peer.sin_port;
            bool free_owner=!owner_valid || !pcm.active || now-pcm.last_ms>300;
            uint32_t previous_session=pcm.session;
            accepted=(same_peer || free_owner) && wifi_pcm_push(&pcm,packet,(size_t)n,now);
            if(accepted) {
                if(!same_peer || free_owner || previous_session!=pcm.session) {generation++;return_sequence=0;}
                owner=peer;owner_valid=pcm.active;
                duplex=pcm.active && packet[14]==2;
                if(!pcm.active) generation++;
            }
            vs_mic_trace_source(pcm.count);
            full=duplex;
            reply[0]=full?0x32415356:0x31415356; reply[1]=pcm.received; reply[2]=pcm.underruns; reply[3]=(uint32_t)pcm.count;
            reply[4]=return_sent;reply[5]=return_dropped;
            portEXIT_CRITICAL(&pcm_lock);
            if(accepted && reply[1]%10==0) sendto(fd,reply,full?24:16,0,(struct sockaddr*)&peer,peer_len);
        }
        // Bound work so incoming microphone packets are serviced every iteration.
        for(int i=0;i<8 && xQueueReceive(return_queue,&block,0)==pdTRUE;i++) {
            struct sockaddr_in target;
            int64_t now=esp_timer_get_time()/1000;
            portENTER_CRITICAL(&pcm_lock);
            bool listening=owner_valid && duplex && pcm.active && now-pcm.last_ms<=300 && block.session==pcm.session && block.generation==generation;
            bool fresh=now-block.created_ms<=80;
            if(!listening) return_invalid++; else if(!fresh) return_stale++;
            target=owner;
            portEXIT_CRITICAL(&pcm_lock);
            if(!listening || !fresh) continue;
            memcpy(back,"VSR1",4);
            memcpy(back+4,&block.session,4);memcpy(back+8,&return_sequence,4);return_sequence++;
            back[12]=0xe0;back[13]=1;back[14]=back[15]=0;memcpy(back+16,block.data,960);
            int sent=sendto(fd,back,sizeof back,0,(struct sockaddr*)&target,sizeof target);
            portENTER_CRITICAL(&pcm_lock);
            if(sent==(int)sizeof back)return_sent++;else return_dropped++;
            portEXIT_CRITICAL(&pcm_lock);
        }
    }
}
static esp_err_t root_get(httpd_req_t *req) { httpd_resp_set_type(req,"text/html; charset=utf-8");return httpd_resp_send(req,page,HTTPD_RESP_USE_STRLEN); }
static bool mic_trace_json(cJSON *usb) {
    if (!vs_mic_trace_enabled()) {
        cJSON *trace=cJSON_AddObjectToObject(usb,"mic_trace");
        return trace && cJSON_AddBoolToObject(trace,"enabled",false);
    }
    // HTTP task only: keep the event ring off its small stack.
    vs_mic_trace_t *snapshot=malloc(sizeof(*snapshot));
    if(!snapshot)return false;
    vs_mic_trace_snapshot(snapshot);
    cJSON *trace=cJSON_AddObjectToObject(usb,"mic_trace");
    if(!trace){free(snapshot);return false;}
    cJSON_AddBoolToObject(trace,"enabled",true);
#define TRACE_FIELD(key) cJSON_AddNumberToObject(trace,#key,snapshot->key)
    TRACE_FIELD(stream);TRACE_FIELD(planned_empty);TRACE_FIELD(completed_empty);
    TRACE_FIELD(slow_producer);TRACE_FIELD(plans);TRACE_FIELD(publications);
    TRACE_FIELD(max_plan_gap_us);TRACE_FIELD(max_wake_us);TRACE_FIELD(max_render_us);
    TRACE_FIELD(fifo_bytes);TRACE_FIELD(requested_bytes);TRACE_FIELD(staged_bytes);
    TRACE_FIELD(source_frames);TRACE_FIELD(phase);TRACE_FIELD(event_count);
#undef TRACE_FIELD
    unsigned count=snapshot->event_count<VS_MIC_TRACE_CAPACITY?snapshot->event_count:VS_MIC_TRACE_CAPACITY;
    cJSON_AddNumberToObject(trace,"overwritten_events",snapshot->event_count-count);
    cJSON *events=cJSON_AddArrayToObject(trace,"events");
    if(!events){free(snapshot);return false;}
    for(unsigned i=0;i<count;i++){
        const vs_mic_event_t *e=&snapshot->events[(snapshot->event_count-count+i)%VS_MIC_TRACE_CAPACITY];
        cJSON *item=cJSON_CreateObject();
        if(!item){free(snapshot);return false;}
        cJSON_AddItemToArray(events,item);
#define EVENT_FIELD(key) cJSON_AddNumberToObject(item,#key,(double)e->key)
        EVENT_FIELD(at_us);EVENT_FIELD(sequence);EVENT_FIELD(kind);EVENT_FIELD(stream);
        EVENT_FIELD(stream_age_us);EVENT_FIELD(fifo_bytes);EVENT_FIELD(requested_bytes);
        EVENT_FIELD(staged_bytes);EVENT_FIELD(source_frames);EVENT_FIELD(phase);
        EVENT_FIELD(request_age_us);EVENT_FIELD(wake_us);EVENT_FIELD(render_us);EVENT_FIELD(mic_active);EVENT_FIELD(speaker_active);
#undef EVENT_FIELD
    }
    free(snapshot);return true;
}
static esp_err_t status_get(httpd_req_t *req) {
    esp_netif_ip_info_t info={0}; esp_netif_get_ip_info(station,&info);
    uint32_t received,underruns,returned,dropped,gaps,trimmed,squeezed,stretched,flushed; size_t count; int adjust;
    portENTER_CRITICAL(&pcm_lock); received=pcm.received;underruns=pcm.underruns;count=pcm.count;returned=return_sent;dropped=return_dropped;gaps=pcm.gaps;trimmed=pcm.dropped;
    squeezed=pcm.squeezed;stretched=pcm.stretched;adjust=pcm.adjust;flushed=pcm.flushed;portEXIT_CRITICAL(&pcm_lock);
    char json[380];snprintf(json,sizeof json,"{\"router_ip\":\"" IPSTR "\",\"direct_ip\":\"192.168.4.1\",\"udp_port\":49152,\"protocol\":\"duplex-v1\",\"usb_mode\":\"%s\",\"received\":%lu,\"underruns\":%lu,\"buffer_ms\":%u,\"returned\":%lu,\"return_dropped\":%lu}",IP2STR(&info.ip),vs_usb_mode_name(),(unsigned long)received,(unsigned long)underruns,(unsigned)(count/48),(unsigned long)returned,(unsigned long)dropped);
    cJSON *root=cJSON_Parse(json);
    if(!root)return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"Diagnostic allocation failed");
    cJSON_AddBoolToObject(root,"usb_feedback_enabled",!vs_usb_adaptive_out());
    cJSON_AddStringToObject(root,"usb_out_sync",vs_usb_adaptive_out()?"adaptive":"asynchronous");
    cJSON_AddNumberToObject(root,"input_sequence_gaps",gaps);
    cJSON_AddNumberToObject(root,"input_trimmed_frames",trimmed);
    // level control: frames removed/added so far, and this second's step (+1 drains, -1 fills)
    cJSON_AddNumberToObject(root,"input_level_removed_frames",squeezed);
    cJSON_AddNumberToObject(root,"input_level_added_frames",stretched);
    cJSON_AddNumberToObject(root,"input_level_step",adjust);
    // backlog skipped when the USB host (re)started reading, before anything played
    cJSON_AddNumberToObject(root,"input_start_flushed_frames",flushed);
    uint32_t partial,stale,invalid;
    portENTER_CRITICAL(&pcm_lock);partial=return_partial_frames;stale=return_stale;invalid=return_invalid;portEXIT_CRITICAL(&pcm_lock);
    cJSON_AddNumberToObject(root,"return_partial_frames",partial);
    cJSON_AddNumberToObject(root,"return_stale",stale);
    cJSON_AddNumberToObject(root,"return_invalid",invalid);
    cJSON *usb=cJSON_AddObjectToObject(root,"usb");
    if(!usb){cJSON_Delete(root);return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"Diagnostic allocation failed");}
    vs_usb_stats_t stats=vs_usb_diag_snapshot();
    cJSON_AddNumberToObject(usb,"version",6);
    cJSON_AddNumberToObject(usb,"uptime_ms",(double)(uint32_t)(esp_timer_get_time()/1000));
    cJSON_AddNumberToObject(usb,"mic_prefill_attempts",stats.mic_prefill_attempts);
    cJSON_AddNumberToObject(usb,"mic_prefill_recovered",stats.mic_prefill_recovered);
    cJSON_AddBoolToObject(usb,"mic_active",stats.mic_active);
    cJSON_AddBoolToObject(usb,"speaker_active",stats.speaker_active);
    cJSON_AddNumberToObject(usb,"feedback_value_16_16",stats.feedback_value);
    cJSON_AddNumberToObject(usb,"feedback_packet_bytes",stats.feedback_bytes);
    cJSON_AddNumberToObject(usb,"speaker_chunks",stats.spk_chunks);
    cJSON_AddNumberToObject(usb,"speaker_zero_chunks",stats.spk_zero_chunks);
    cJSON_AddNumberToObject(usb,"speaker_zero_after_sound",stats.spk_zero_after_sound);
    cJSON_AddNumberToObject(usb,"speaker_queue_full",stats.spk_queue_full);
    cJSON_AddNumberToObject(usb,"speaker_restarts",stats.spk_restarts);
    const char *names[]={"mic","speaker","feedback"};
    for(unsigned i=0;i<3;i++){
        cJSON *ep=cJSON_AddObjectToObject(usb,names[i]);
        if(!ep){cJSON_Delete(root);return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"Diagnostic allocation failed");}
        cJSON_AddNumberToObject(ep,"completed",stats.ep[i].packets);
        cJSON_AddNumberToObject(ep,"failed",stats.ep[i].failed);
        cJSON_AddNumberToObject(ep,"retries",stats.ep[i].retries);
        cJSON_AddNumberToObject(ep,"zero",stats.ep[i].zero);
        cJSON_AddNumberToObject(ep,"short",stats.ep[i].partial);
        cJSON_AddNumberToObject(ep,"bytes",stats.ep[i].bytes);
    }
    // the last USB anomalies, oldest first, timed by uptime_ms: empty/short microphone packets, failures, retries
    static const char *kinds[]={"","empty","short","failed","retry"};
    cJSON_AddNumberToObject(usb,"event_count",stats.event_count);
    cJSON *events=cJSON_AddArrayToObject(usb,"events");
    if(!events){cJSON_Delete(root);return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"Diagnostic allocation failed");}
    unsigned kept=stats.event_count<VS_USB_EVENTS?stats.event_count:VS_USB_EVENTS;
    for(unsigned i=0;i<kept;i++){
        const vs_usb_event_t *e=&stats.events[(stats.event_count-kept+i)%VS_USB_EVENTS];
        cJSON *item=cJSON_CreateObject();
        if(!item){cJSON_Delete(root);return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"Diagnostic allocation failed");}
        cJSON_AddNumberToObject(item,"at_ms",e->at_ms);
        cJSON_AddStringToObject(item,"kind",e->kind<5?kinds[e->kind]:"?");
        cJSON_AddStringToObject(item,"endpoint",e->endpoint<3?names[e->endpoint]:"?");
        cJSON_AddNumberToObject(item,"bytes",e->bytes);
        cJSON_AddItemToArray(events,item);
    }
    if(!mic_trace_json(usb)){cJSON_Delete(root);return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"Trace allocation failed");}
    char *body=cJSON_PrintUnformatted(root);cJSON_Delete(root);
    if(!body)return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"Diagnostic allocation failed");
    httpd_resp_set_type(req,"application/json");
    esp_err_t result=httpd_resp_send(req,body,HTTPD_RESP_USE_STRLEN);cJSON_free(body);return result;
}
// Changing settings needs the board's own Wi-Fi, whose password only the owner has; the router side reads /status.
static bool from_board_ap(httpd_req_t *req) {
    struct sockaddr_storage local; socklen_t len=sizeof local; uint32_t address;
    if(getsockname(httpd_req_to_sockfd(req),(struct sockaddr*)&local,&len)!=0) return false;
    if(local.ss_family==AF_INET) address=((struct sockaddr_in*)&local)->sin_addr.s_addr;
    else if(local.ss_family==AF_INET6) {  // a dual-stack server sees IPv4 as ::ffff:a.b.c.d
        const uint8_t *v6=((struct sockaddr_in6*)&local)->sin6_addr.s6_addr;
        static const uint8_t mapped[12]={0,0,0,0,0,0,0,0,0,0,0xff,0xff};
        if(memcmp(v6,mapped,12)) return false;
        memcpy(&address,v6+12,4);
    } else return false;
    esp_netif_ip_info_t info={0};
    return esp_netif_get_ip_info(access_point,&info)==ESP_OK && info.ip.addr && address==info.ip.addr;
}
static esp_err_t not_from_ap(httpd_req_t *req) {
    httpd_resp_set_status(req,"403 Forbidden");
    return httpd_resp_sendstr(req,"Connect to the board's own Wi-Fi to change settings, or use the setup program over COM.");
}
static esp_err_t wifi_post(httpd_req_t *req) {
    if(!from_board_ap(req)) return not_from_ap(req);
    if(req->content_len<=0 || req->content_len>240) return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Invalid size");
    char body[241];int got=0;
    while(got<req->content_len) {int n=httpd_req_recv(req,body+got,req->content_len-got);if(n<=0)return ESP_FAIL;got+=n;}body[got]=0;
    cJSON *json=cJSON_Parse(body), *ssid=cJSON_GetObjectItemCaseSensitive(json,"ssid"), *password=cJSON_GetObjectItemCaseSensitive(json,"password");
    if(!cJSON_IsString(ssid)||!cJSON_IsString(password)||strlen(ssid->valuestring)==0||strlen(ssid->valuestring)>32||strlen(password->valuestring)>63||(strlen(password->valuestring)>0&&strlen(password->valuestring)<8)) {
        cJSON_Delete(json);return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Check SSID and password (8-63 characters, or empty)");
    }
    esp_err_t error=wifi_bridge_set_station(ssid->valuestring,password->valuestring);
    cJSON_Delete(json);
    if(error!=ESP_OK)return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"Could not save Wi-Fi");
    return httpd_resp_sendstr(req,"Saved. Router IP will appear below; then reconnect your phone to that Wi-Fi.");
}
esp_err_t wifi_bridge_set_station(const char *ssid, const char *password) {
    nvs_handle_t handle;esp_err_t error=nvs_open("vs_wifi",NVS_READWRITE,&handle);
    if(error!=ESP_OK)return error;
    if(*ssid){error=nvs_set_str(handle,"ssid",ssid);if(error==ESP_OK)error=nvs_set_str(handle,"password",password);}
    else error=nvs_erase_all(handle);
    if(error==ESP_OK)error=nvs_commit(handle);
    nvs_close(handle);
    if(error!=ESP_OK)return error;
    wifi_config_t cfg={0};memcpy(cfg.sta.ssid,ssid,strlen(ssid));memcpy(cfg.sta.password,password,strlen(password));
    configured=false;esp_wifi_disconnect();error=esp_wifi_set_config(WIFI_IF_STA,&cfg);
    if(error!=ESP_OK||!*ssid)return error;
    configured=true;esp_wifi_connect();  // joins in the background; router_ip shows when it has
    return ESP_OK;
}
bool wifi_bridge_station(char ssid[33], char ip[16]) {
    wifi_config_t cfg={0};wifi_ap_record_t joined;esp_netif_ip_info_t info={0};
    ssid[0]=ip[0]=0;
    if(esp_wifi_get_config(WIFI_IF_STA,&cfg)==ESP_OK){memcpy(ssid,cfg.sta.ssid,32);ssid[32]=0;}
    if(esp_wifi_sta_get_ap_info(&joined)!=ESP_OK||esp_netif_get_ip_info(station,&info)!=ESP_OK||!info.ip.addr)return false;
    snprintf(ip,16,IPSTR,IP2STR(&info.ip));return true;
}
static void ap_config(wifi_config_t *ap) {
    memset(ap,0,sizeof *ap);
    const char *name=board_ap_ssid(),*pass=board_ap_password();
    memcpy(ap->ap.ssid,name,strlen(name));ap->ap.ssid_len=(uint8_t)strlen(name);
    memcpy(ap->ap.password,pass,strlen(pass));
    ap->ap.channel=6;ap->ap.authmode=WIFI_AUTH_WPA2_PSK;ap->ap.max_connection=2;
}
esp_err_t wifi_bridge_apply_ap(void) { wifi_config_t ap;ap_config(&ap);return esp_wifi_set_config(WIFI_IF_AP,&ap); }
static esp_err_t usb_mode_post(httpd_req_t *req) {
    if(!from_board_ap(req)) return not_from_ap(req);
    if(req->content_len!=5 && req->content_len!=8) return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Expected apple, standard or adaptive");
    char mode[9]={0};int got=0;
    while(got<req->content_len){int n=httpd_req_recv(req,mode+got,req->content_len-got);if(n<=0)return ESP_FAIL;got+=n;}
    if(strcmp(mode,"apple") && strcmp(mode,"standard") && strcmp(mode,"adaptive"))return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Unknown USB mode");
    if(usb_profile_save(!strcmp(mode,"adaptive")?VS_USB_ADAPTIVE:!strcmp(mode,"apple")?VS_USB_APPLE:VS_USB_STANDARD)!=ESP_OK)return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"Could not save USB mode");
    return httpd_resp_sendstr(req,"Saved. Unplug BOTH USB and COM cables, then reconnect USB to the device. Wi-Fi settings are retained. Active usb_mode changes after reboot.");
}
static void event(void *arg,esp_event_base_t base,int32_t id,void *data) {
    (void)arg;
    if(base==WIFI_EVENT && (id==WIFI_EVENT_STA_START||id==WIFI_EVENT_STA_DISCONNECTED) && configured)esp_wifi_connect();
    if(base==IP_EVENT && id==IP_EVENT_STA_GOT_IP) {ip_event_got_ip_t *e=data;ESP_LOGI(TAG,"ROUTER IP: " IPSTR,IP2STR(&e->ip_info.ip));}
}
void wifi_bridge_init(void) {
    return_queue=xQueueCreate(8,sizeof(return_audio_t));
    ESP_ERROR_CHECK(return_queue?ESP_OK:ESP_ERR_NO_MEM);
    esp_err_t err=nvs_flash_init();
    if(err==ESP_ERR_NVS_NO_FREE_PAGES||err==ESP_ERR_NVS_NEW_VERSION_FOUND){ESP_ERROR_CHECK(nvs_flash_erase());err=nvs_flash_init();}ESP_ERROR_CHECK(err);
    board_config_load();
    ESP_ERROR_CHECK(esp_netif_init());ESP_ERROR_CHECK(esp_event_loop_create_default());
    access_point=esp_netif_create_default_wifi_ap();station=esp_netif_create_default_wifi_sta();
    wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,event,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,event,NULL));
    wifi_config_t ap;ap_config(&ap);
    wifi_config_t sta={0};nvs_handle_t h;
    if(nvs_open("vs_wifi",NVS_READONLY,&h)==ESP_OK){char ssid[33]={0},pass[64]={0};size_t a=sizeof ssid,b=sizeof pass;configured=nvs_get_str(h,"ssid",ssid,&a)==ESP_OK&&nvs_get_str(h,"password",pass,&b)==ESP_OK;if(configured){memcpy(sta.sta.ssid,ssid,strlen(ssid));memcpy(sta.sta.password,pass,strlen(pass));}nvs_close(h);}
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP,&ap));
    if(configured)ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA,&sta));
    ESP_ERROR_CHECK(esp_wifi_start());ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    httpd_handle_t server;httpd_config_t config=HTTPD_DEFAULT_CONFIG();config.stack_size=6144;
    // HTTPD reserves three sockets; leave capacity for UDP audio and new accepts.
    // Browser/status clients may retain idle connections across polls.
    config.max_open_sockets=4;
    config.lru_purge_enable=true;
    config.recv_wait_timeout=3;
    config.send_wait_timeout=3;
    ESP_ERROR_CHECK(httpd_start(&server,&config));
    httpd_uri_t root={.uri="/",.method=HTTP_GET,.handler=root_get};httpd_uri_t status={.uri="/status",.method=HTTP_GET,.handler=status_get};httpd_uri_t setup={.uri="/wifi",.method=HTTP_POST,.handler=wifi_post};
    ESP_ERROR_CHECK(httpd_register_uri_handler(server,&root));ESP_ERROR_CHECK(httpd_register_uri_handler(server,&status));ESP_ERROR_CHECK(httpd_register_uri_handler(server,&setup));
    httpd_uri_t usb_mode={.uri="/usb-mode",.method=HTTP_POST,.handler=usb_mode_post};
    ESP_ERROR_CHECK(httpd_register_uri_handler(server,&usb_mode));
    ESP_ERROR_CHECK(xTaskCreate(udp_task,"wifi_pcm",8192,NULL,4,NULL)==pdPASS ? ESP_OK : ESP_ERR_NO_MEM);
    ESP_LOGI(TAG,"READY: board Wi-Fi %s (password: setup program, or @get on COM) ; setup http://192.168.4.1 ; PCM UDP 49152",board_ap_ssid());
}
