using UnityEngine;

// 차량 모델이 없을 때 쓰는 상자 차량 + 바닥 평면 + 따라가는 카메라.
// 공개 저장소(autodrive_digital_twin)에는 받은 차량 3D 모델·가우시안 스플랫을 넣지 않으므로, 씬에 'car'가 없으면
// TwinBootstrap이 Play 시점에 이걸로 차를 만든다(씬 파일 불필요 — 빈 씬에서 Play만 누르면 된다).
// 치수는 실차 실측: 휠베이스 0.545 m, 윤거 0.43 m, 바퀴 반지름 0.1 m. 앞 = +Z (TwinFirmware의 진행 방향과 같음).
// 앞바퀴는 이름이 FrontLeftWheel/FrontRightWheel인 피벗(조향축) 아래에 있어 TwinFirmware가 그대로 돌린다.
public static class TwinPlaceholder
{
    const float Wheelbase = 0.545f, Track = 0.43f, WheelR = 0.10f, WheelW = 0.06f;

    public static GameObject Build(string name)
    {
        // 바닥: 30 m × 30 m 평면 + 1 m 격자선(움직임이 보이도록)
        var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
        ground.name = "Ground (placeholder)";
        ground.transform.localScale = new Vector3(3f, 1f, 3f);
        Paint(ground, new Color(0.82f, 0.84f, 0.86f));
        var grid = new GameObject("Grid");
        for (int i = -15; i <= 15; i++)
        {
            Line(grid.transform, new Vector3(i, 0.002f, 0f), new Vector3(0.01f, 0.001f, 30f), i == 0 ? Color.gray : new Color(0.7f, 0.72f, 0.75f));
            Line(grid.transform, new Vector3(0f, 0.002f, i), new Vector3(30f, 0.001f, 0.01f), i == 0 ? Color.gray : new Color(0.7f, 0.72f, 0.75f));
        }

        // 차체
        var car = new GameObject(name);
        Box(car.transform, "Body", new Vector3(0f, 0.20f, 0.02f), new Vector3(Track - 0.02f, 0.14f, Wheelbase + 0.20f), new Color(0.85f, 0.20f, 0.25f));
        Box(car.transform, "Deck", new Vector3(0f, 0.31f, -0.05f), new Vector3(0.30f, 0.08f, 0.40f), new Color(0.25f, 0.25f, 0.28f));
        Box(car.transform, "Nose (front)", new Vector3(0f, 0.20f, Wheelbase / 2f + 0.13f), new Vector3(0.20f, 0.06f, 0.04f), Color.white);

        // 바퀴: 뒤 2개는 고정, 앞 2개는 피벗(조향축) 아래
        for (int side = -1; side <= 1; side += 2)
        {
            Wheel(car.transform, new Vector3(side * Track / 2f, WheelR, -Wheelbase / 2f));
            var pivot = new GameObject(side < 0 ? "FrontLeftWheel" : "FrontRightWheel").transform;
            pivot.SetParent(car.transform, false);
            pivot.localPosition = new Vector3(side * Track / 2f, WheelR, Wheelbase / 2f);
            Wheel(pivot, Vector3.zero);
        }

        // 조명·카메라
        if (Object.FindAnyObjectByType<Light>() == null)
        {
            var light = new GameObject("Directional Light").AddComponent<Light>();
            light.type = LightType.Directional;
            light.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
        }
        var cam = Camera.main;
        if (cam == null)
        {
            cam = new GameObject("Main Camera").AddComponent<Camera>();
            cam.tag = "MainCamera";
        }
        cam.backgroundColor = new Color(0.93f, 0.95f, 0.97f);
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.gameObject.AddComponent<TwinFollowCamera>().target = car.transform;
        Debug.Log("[TwinPlaceholder] 차량 모델이 없어 상자 차량·바닥 평면으로 실행 (실차 치수)");
        return car;
    }

    static void Wheel(Transform parent, Vector3 pos)
    {
        var w = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        w.name = "Tire";
        Object.Destroy(w.GetComponent<Collider>());
        w.transform.SetParent(parent, false);
        w.transform.localPosition = pos;
        w.transform.localRotation = Quaternion.Euler(0f, 0f, 90f);           // 원통 축을 차축(X) 방향으로
        w.transform.localScale = new Vector3(WheelR * 2f, WheelW / 2f, WheelR * 2f);
        Paint(w, new Color(0.12f, 0.12f, 0.12f));
    }

    static void Box(Transform parent, string name, Vector3 pos, Vector3 size, Color c)
    {
        var b = GameObject.CreatePrimitive(PrimitiveType.Cube);
        b.name = name;
        Object.Destroy(b.GetComponent<Collider>());
        b.transform.SetParent(parent, false);
        b.transform.localPosition = pos;
        b.transform.localScale = size;
        Paint(b, c);
    }

    static void Line(Transform parent, Vector3 pos, Vector3 size, Color c)
    {
        var l = GameObject.CreatePrimitive(PrimitiveType.Cube);
        Object.Destroy(l.GetComponent<Collider>());
        l.transform.SetParent(parent, false);
        l.transform.localPosition = pos;
        l.transform.localScale = size;
        Paint(l, c);
    }

    static void Paint(GameObject g, Color c)
    {
        var r = g.GetComponent<Renderer>();
        if (r != null) r.material.color = c;
    }
}

// 차 뒤쪽 위에서 따라가는 카메라 (상자 차량용)
public class TwinFollowCamera : MonoBehaviour
{
    public Transform target;
    public Vector3 offset = new Vector3(0f, 1.1f, -1.6f);

    void LateUpdate()
    {
        if (!target) return;
        var want = target.position + target.rotation * offset;
        transform.position = Vector3.Lerp(transform.position, want, 1f - Mathf.Exp(-6f * Time.deltaTime));
        transform.LookAt(target.position + Vector3.up * 0.15f);
    }
}
