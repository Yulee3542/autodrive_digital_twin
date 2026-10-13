using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using Debug = UnityEngine.Debug;

// 디지털 트윈: 차량/컨트롤 패널 펌웨어(autodrive_skku arduino/car_controller/car_controller.ino)와
// 같은 바이트 명령을 TCP로 받아 같은 규칙으로 움직이고 같은 형식으로 응답한다.
//   PC→MCU: G/1 주행 허용(V 전이면 기본 속도 100) · 2 후진 · S/3 정지 · V<int>\n 속도 · L/R 120 ms 조향 펄스 · F 조향 정지
//   MCU→PC: 0/1/2 상태(변화 시 또는 100 ms마다) · P <adc> 조향 POT(50 ms마다)
//   아무 바이트나 받으면 워치독 갱신(V를 받은 뒤 500 ms 두절이면 속도 0). 조향은 G와 무관. 펄스 중 L/R이 또 오면 연장.
// ROS 2 쪽은 kiis_testbed의 arduino_node를 port:=socket://<윈도우IP>:55002 로 하나 더 띄워 붙인다 —
// 패널 브리지와 같은 /car/cmd/*를 받고 응답만 /twin/car/*로 발행된다.
// 펌웨어 루프는 별도 스레드에서 1 ms 주기로 돌고(Unity 프레임과 무관), 화면은 그 상태를 읽어 그린다.
// 같은 규칙의 파이썬 모델: twin/firmware_model.py — 둘을 바꿀 때는 함께 바꿀 것.
// 붙일 곳: Hierarchy의 car (TwinBootstrap이 Play 시 자동으로 붙인다). 켜지면 CarStateReceiver는 끈다.
public class TwinFirmware : MonoBehaviour
{
    [Serializable]
    public class Params
    {
        public float steer_pulse_ms = 120f;
        public float deg_per_pulse = 6.0f;      // 120 ms 펄스 — 07-28 실측 6.1~12.2 deg(기어 교체 전) 하한. 패널 실측으로 피팅
        public float steer_lag_ms = 0f;
        public float backlash_deg = 0f;
        public float steer_limit_deg = 20f;
        public float pot_left_adc = 825f;       // arduino_node.adc_to_deg와 같은 좌/우 2점 선형 매핑
        public float pot_right_adc = 146f;
        public float[] speed_calibration_pwm = { 15, 20, 25, 50, 75, 100, 125, 140, 150, 255 };
        public float[] speed_calibration_mps = { 0f, 0.0667f, 0.120f, 0.3408f, 0.5033f, 0.6167f, 0.6875f, 0.720f, 0.735f, 1.00f };
        public float wheelbase_m = 0.54f;
    }

    [Header("통신 (WSL2의 ROS 2에서 붙으므로 0.0.0.0)")]
    public string ip = "0.0.0.0";
    public int port = 55002;

    [Header("파라미터 (비우면 twin/twin_params.json → 없으면 기본값)")]
    public string paramsPath = "";
    public Params p = new Params();

    [Header("모델 정렬")]
    public Transform frontLeftWheel;
    public Transform frontRightWheel;

    [Header("상태 (확인용)")]
    public bool clientConnected;
    public bool canGo;
    public int speedCmd;
    public float steeringDeg;
    public float speedMps;

    const int DEFAULT_SPEED = 100, WATCHDOG_MS = 500, STATUS_PRINT_MS = 100, POT_PRINT_MS = 50, PARSE_INT_TIMEOUT_MS = 20;

    // ---- 펌웨어 상태 (펌웨어 스레드 전용) ----
    long t;
    bool fwCanGo, useSerialSpeed, readingV;
    int cmdSpeed, lastState = -1;
    long lastSerial, lastStatusMs = -1000000, lastPotMs = -1000000, steerStart = -1, vStart;
    readonly StringBuilder vDigits = new StringBuilder();
    // ---- 기구 ----
    float angle, slack;
    int lastMoveDir;
    readonly List<KeyValuePair<long, int>> motorHist = new List<KeyValuePair<long, int>>();
    float px, pz, heading;

    readonly ConcurrentQueue<byte> rx = new ConcurrentQueue<byte>();
    readonly ConcurrentQueue<string> tx = new ConcurrentQueue<string>();
    readonly object stateLock = new object();
    Thread netThread, fwThread;
    volatile bool running;
    TcpListener listener;
    TcpClient client;
    volatile bool centerRequested;   // C 키 → 펌웨어 스레드가 조향·위치를 0으로 (실험 run 사이 초기화)

    Vector3 startPos;
    float startHeading;
    Quaternion flBase, frBase;

    void Start()
    {
        Application.runInBackground = true;
        LoadParams();
        // MATLAB 상태 수신기(CarStateReceiver — 받은 차량 프로젝트에 들어 있던 스크립트, 공개 저장소엔 없음)가 붙어 있으면
        // 바퀴 참조를 빌려 오고 끈다. 타입을 직접 참조하지 않아 그 스크립트가 없어도 컴파일된다.
        var recv = GetComponent("CarStateReceiver") as Behaviour;
        if (recv != null)
        {
            var t = recv.GetType();
            if (frontLeftWheel == null) frontLeftWheel = t.GetField("frontLeftWheel")?.GetValue(recv) as Transform;
            if (frontRightWheel == null) frontRightWheel = t.GetField("frontRightWheel")?.GetValue(recv) as Transform;
            recv.enabled = false;
        }
        // 상자 차량(TwinPlaceholder) 등: 자식 이름으로 찾는다
        if (frontLeftWheel == null) frontLeftWheel = transform.Find("FrontLeftWheel");
        if (frontRightWheel == null) frontRightWheel = transform.Find("FrontRightWheel");
        var rb = GetComponent<Rigidbody>();
        if (rb != null) rb.isKinematic = true;
        startPos = transform.position;
        startHeading = transform.eulerAngles.y;
        if (frontLeftWheel) flBase = frontLeftWheel.localRotation;
        if (frontRightWheel) frBase = frontRightWheel.localRotation;

        running = true;
        PrintState(0);
        netThread = new Thread(NetLoop) { IsBackground = true };
        fwThread = new Thread(FirmwareLoop) { IsBackground = true, Priority = System.Threading.ThreadPriority.AboveNormal };
        netThread.Start();
        fwThread.Start();
    }

    void LoadParams()
    {
        string path = string.IsNullOrEmpty(paramsPath)
            ? Path.GetFullPath(Path.Combine(Application.dataPath, "../../../twin/twin_params.json"))
            : paramsPath;
        if (File.Exists(path))
        {
            JsonUtility.FromJsonOverwrite(File.ReadAllText(path), p);
            Debug.Log($"[TwinFirmware] 파라미터: {path} (deg_per_pulse={p.deg_per_pulse}, lag={p.steer_lag_ms} ms, backlash={p.backlash_deg})");
        }
        else Debug.Log($"[TwinFirmware] {path} 없음 → 기본값 사용");
    }

    // ---------------------------------------------------------------- 통신 스레드
    void NetLoop()
    {
        try
        {
            listener = new TcpListener(IPAddress.Parse(ip), port);
            // 독점 사용: 윈도우에서 ReuseAddress면 Unity 두 개가 같은 포트를 열어 브리지가 엉뚱한 쪽에 붙을 수 있다
            listener.ExclusiveAddressUse = true;
            listener.Start();
            Debug.Log($"[TwinFirmware] {ip}:{port} 대기 중");
        }
        catch (Exception e) { Debug.LogError($"[TwinFirmware] 포트를 열 수 없음: {e.Message}"); return; }

        var buf = new byte[1024];
        while (running)
        {
            try
            {
                client = listener.AcceptTcpClient();
                client.NoDelay = true;
                while (tx.TryDequeue(out _)) { }   // 연결 전에 쌓인 응답은 버린다
                clientConnected = true;
                var s = client.GetStream();
                while (running && client.Connected)
                {
                    while (tx.TryDequeue(out var line))
                    {
                        var b = Encoding.ASCII.GetBytes(line + "\r\n");   // Serial.println과 같은 줄끝
                        s.Write(b, 0, b.Length);
                    }
                    if (s.DataAvailable)
                    {
                        int n = s.Read(buf, 0, buf.Length);
                        if (n <= 0) break;
                        for (int i = 0; i < n; i++) rx.Enqueue(buf[i]);
                    }
                    else Thread.Sleep(1);
                    if (client.Client.Poll(0, SelectMode.SelectRead) && client.Available == 0) break;
                }
            }
            catch (Exception) { if (!running) break; Thread.Sleep(50); }
            finally
            {
                clientConnected = false;
                try { client?.Close(); } catch { }
                client = null;
            }
        }
    }

    void Emit(string s) { if (clientConnected) tx.Enqueue(s); }

    // ---------------------------------------------------------------- 펌웨어 스레드 (1 ms)
    void FirmwareLoop()
    {
        var sw = Stopwatch.StartNew();
        while (running)
        {
            long target = sw.ElapsedMilliseconds;
            while (t < target)
            {
                while (rx.TryDequeue(out byte b)) HandleByte((char)b);
                Tick();
            }
            Thread.Sleep(1);
        }
    }

    void FinishV()
    {
        string s = vDigits.ToString();
        int v = 0;
        if (s.Length > 0 && s != "-") int.TryParse(s, out v);
        cmdSpeed = Mathf.Clamp(v, -255, 255);
        useSerialSpeed = true;
        readingV = false;
        vDigits.Length = 0;
    }

    void HandleByte(char c)
    {
        lastSerial = t;
        if (readingV)
        {
            if (char.IsDigit(c) || (c == '-' && vDigits.Length == 0)) { vDigits.Append(c); return; }
            if (vDigits.Length == 0) return;          // parseInt는 숫자 전의 비숫자를 버린다
            FinishV();                                 // 끝낸 문자는 소비하지 않고 아래에서 명령으로 처리
        }
        switch (c)
        {
            case 'G': case '1': fwCanGo = true; if (!useSerialSpeed) cmdSpeed = DEFAULT_SPEED; break;
            case '2': fwCanGo = true; if (!useSerialSpeed) cmdSpeed = -DEFAULT_SPEED; break;
            case 'S': case '3': fwCanGo = false; break;
            case 'V': readingV = true; vDigits.Length = 0; vStart = t; break;
            case 'F': steerStart = -1; Motor(0); break;
            case 'L': steerStart = t; Motor(+1); break;   // 'L' = 좌회전 요청(좌 = +)
            case 'R': steerStart = t; Motor(-1); break;
        }
    }

    void Motor(int d) => motorHist.Add(new KeyValuePair<long, int>(t, d));

    void PrintState(int st)
    {
        if (st != lastState || t - lastStatusMs >= STATUS_PRINT_MS)
        {
            Emit(st.ToString()); lastState = st; lastStatusMs = t;
        }
    }

    int AngleToAdc(float deg)
    {
        float adc = p.pot_right_adc + (deg + p.steer_limit_deg) / (2f * p.steer_limit_deg) * (p.pot_left_adc - p.pot_right_adc);
        return Mathf.Clamp(Mathf.RoundToInt(adc), 0, 1023);
    }

    float PwmToSpeed(int pwm)
    {
        var xs = p.speed_calibration_pwm; var ys = p.speed_calibration_mps;
        float a = Mathf.Abs(pwm), v;
        if (a <= xs[0]) v = 0f;
        else if (a >= xs[xs.Length - 1]) v = ys[ys.Length - 1];
        else
        {
            int i = 1;
            while (a > xs[i]) i++;
            v = ys[i - 1] + (ys[i] - ys[i - 1]) * (a - xs[i - 1]) / (xs[i] - xs[i - 1]);
        }
        return pwm >= 0 ? v : -v;
    }

    void Tick()
    {
        if (centerRequested)
        {
            centerRequested = false;
            steerStart = -1; motorHist.Clear(); slack = 0f; lastMoveDir = 0;
            lock (stateLock) { angle = 0f; px = pz = heading = 0f; }
        }
        if (readingV && t - vStart >= PARSE_INT_TIMEOUT_MS) FinishV();
        if (steerStart >= 0 && t - steerStart >= p.steer_pulse_ms) { steerStart = -1; Motor(0); }
        bool tripped = useSerialSpeed && t - lastSerial > WATCHDOG_MS;
        int sp = (!fwCanGo || tripped) ? 0 : cmdSpeed;
        PrintState(sp > 0 ? 1 : (sp < 0 ? 2 : 0));
        if (t - lastPotMs >= POT_PRINT_MS) { lastPotMs = t; Emit("P " + AngleToAdc(angle)); }

        // 기구: steer_lag_ms 만큼 지난 모터 상태로 움직인다
        float lagged = t - p.steer_lag_ms;
        int d = 0, keepFrom = 0;
        for (int i = 0; i < motorHist.Count; i++)
        {
            if (motorHist[i].Key <= lagged) { d = motorHist[i].Value; keepFrom = i; }
            else break;
        }
        if (keepFrom > 0) motorHist.RemoveRange(0, keepFrom);
        float v = PwmToSpeed(sp);
        lock (stateLock)
        {
            if (d != 0)
            {
                float step = p.deg_per_pulse / p.steer_pulse_ms;
                if (lastMoveDir != 0 && d != lastMoveDir) slack = p.backlash_deg;
                lastMoveDir = d;
                if (slack > 0f) { float eat = Mathf.Min(slack, step); slack -= eat; step -= eat; }
                angle = Mathf.Clamp(angle + d * step, -p.steer_limit_deg, p.steer_limit_deg);
            }
            // 자전거 모델 1 ms 적분. Unity Y 회전은 위에서 볼 때 시계 방향 → 좌회전(+δ)이면 heading 감소
            float h = (startHeading + heading) * Mathf.Deg2Rad;
            px += Mathf.Sin(h) * v * 0.001f;
            pz += Mathf.Cos(h) * v * 0.001f;
            heading -= v / p.wheelbase_m * Mathf.Tan(angle * Mathf.Deg2Rad) * 0.001f * Mathf.Rad2Deg;
            canGo = fwCanGo; speedCmd = sp; steeringDeg = angle; speedMps = v;
        }
        t++;
    }

    // ---------------------------------------------------------------- 화면
    void Update()
    {
        if (Input.GetKeyDown(KeyCode.C)) centerRequested = true;
        float a, x, z, h;
        lock (stateLock) { a = angle; x = px; z = pz; h = heading; }
        transform.SetPositionAndRotation(startPos + new Vector3(x, 0f, z), Quaternion.Euler(0f, startHeading + h, 0f));
        SteerWheel(frontLeftWheel, flBase, -a);
        SteerWheel(frontRightWheel, frBase, -a);
    }

    void SteerWheel(Transform wheel, Quaternion baseRot, float steerDeg)
    {
        if (!wheel) return;
        Vector3 up = wheel.parent ? wheel.parent.InverseTransformDirection(transform.up) : Vector3.up;
        wheel.localRotation = Quaternion.AngleAxis(steerDeg, up) * baseRot;
    }

    void OnGUI()
    {
        GUI.Box(new Rect(10, 10, 270, 112), "Digital twin (car_controller.ino model)");
        GUI.Label(new Rect(20, 32, 250, 20), $"ROS bridge: {(clientConnected ? "connected" : $"waiting :{port}")}");
        GUI.Label(new Rect(20, 50, 250, 20), $"Go: {canGo}   Speed cmd: {speedCmd}");
        GUI.Label(new Rect(20, 68, 250, 20), $"Steering: {steeringDeg,6:F2} deg   {speedMps,5:F3} m/s");
        GUI.Label(new Rect(20, 86, 250, 20), $"[C] center   pulse {p.deg_per_pulse:F2} deg, lag {p.steer_lag_ms:F0} ms");
    }

    void OnDisable()
    {
        if (!running) return;
        running = false;
        try { listener?.Stop(); } catch { }
        try { client?.Close(); } catch { }
        netThread?.Join(300);
        fwThread?.Join(300);
    }
}
