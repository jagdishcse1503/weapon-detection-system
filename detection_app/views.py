import random
from .models import DetectionRecord, EmailOTP
from .forms import UploadMediaForm, RegisterForm, LoginForm, OTPForm
from django.core.mail import send_mail
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

from django.conf import settings
from django.shortcuts import render, redirect
from django.http import StreamingHttpResponse
from .forms import UploadMediaForm, RegisterForm, LoginForm
from ultralytics import YOLO
import os, cv2, shutil, glob, moviepy as mp
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import DetectionRecord
import csv
from django.core.mail import EmailMessage, send_mail
import time

last_alert_time = 0
# -----------------------------
#  Load YOLO model globally
# -----------------------------
import os

MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "models",
    "best.pt"
)

model = YOLO(MODEL_PATH)

# Ensure media directory exists
os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

# CSV file to store user registration info
CSV_PATH = os.path.join(settings.BASE_DIR, "users.csv")
if not os.path.exists(CSV_PATH):
    with open(CSV_PATH, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['username', 'email', 'password'])

# -----------------------------
#  IMAGE / VIDEO UPLOAD DETECTION
# -----------------------------
@login_required(login_url='login')
def index(request):
    output_image = None
    output_video = None

    if request.method == 'POST':
        form = UploadMediaForm(request.POST, request.FILES)
        if form.is_valid():

            # Clean YOLO runs folder
            for folder in glob.glob("runs/detect/*"):
                shutil.rmtree(folder, ignore_errors=True)

            results = None
            image = form.cleaned_data.get('image')
            video = form.cleaned_data.get('video')

            # -------- IMAGE DETECTION --------
            if image:
                upload_path = os.path.join(settings.MEDIA_ROOT, image.name)
                with open(upload_path, 'wb+') as f:
                    for chunk in image.chunks():
                        f.write(chunk)

                results = model.predict(source=upload_path, conf=0.5, imgsz=640, save=True)

                # Find YOLO output
                exp_dir = results[0].save_dir
                pred_files = glob.glob(os.path.join(exp_dir, '*'))
                if pred_files:
                    pred_file = pred_files[0]
                    output_filename = f"output_{image.name}"
                    output_path = os.path.join(settings.MEDIA_ROOT, output_filename)
                    shutil.move(pred_file, output_path)
                    output_image = f"{settings.MEDIA_URL}{output_filename}"


            # -------- VIDEO DETECTION --------
            elif video:
                upload_path = os.path.join(settings.MEDIA_ROOT, video.name)
                with open(upload_path, 'wb+') as f:
                    for chunk in video.chunks():
                        f.write(chunk)

                results = model.predict(source=upload_path, conf=0.5, imgsz=640, save=True)
                exp_dir = results[0].save_dir
                pred_files = glob.glob(os.path.join(exp_dir, '*'))
                if pred_files:
                    pred_file = pred_files[0]

                    # Convert .avi → .mp4 automatically
                    if pred_file.lower().endswith('.avi'):
                        clip = mp.VideoFileClip(pred_file)
                        mp4_output = pred_file.replace('.avi', '.mp4')
                        clip.write_videofile(mp4_output, codec='libx264', audio_codec='aac')
                        clip.close()
                        os.remove(pred_file)
                        pred_file = mp4_output

                    # Move to MEDIA folder
                    output_filename = f"output_{os.path.basename(pred_file)}"
                    output_path = os.path.join(settings.MEDIA_ROOT, output_filename)
                    shutil.move(pred_file, output_path)
                    output_video = f"{settings.MEDIA_URL}{output_filename}"

            # -----------------------
            #  Save detection record
            # -----------------------
            DetectionRecord.objects.create(
              user=request.user,
              uploaded_file=image if image else video,
              output_file=output_filename,
              file_type='image' if output_image else 'video'
)

            # -----------------------
            #  Email + Dashboard Notification
            # -----------------------
            detected_classes = []
            try:
                res = results[0]
                if hasattr(res, "boxes") and hasattr(res, "names"):
                    cls_indices = []
                    if hasattr(res.boxes, "cls"):
                        import numpy as np
                        cls_indices = [int(x) for x in np.array(res.boxes.cls).reshape(-1)]
                    names_map = res.names
                    for idx in cls_indices:
                        name = names_map.get(idx, str(idx)) if isinstance(names_map, dict) else str(idx)
                        detected_classes.append(str(name).lower())
            except Exception:
                detected_classes = []

            # Check for weapon names
            weapon_keywords = {'knife', 'pistol'}
            found_weapons = sorted({c for c in detected_classes if any(k in c for k in weapon_keywords)})

            if found_weapons and request.user.email:
                subject = "⚠️ Weapon Detection Alert"
                body_lines = [
                    f"Hello {request.user.username},",
                    "",
                    f"A weapon was detected ({', '.join(found_weapons)}).",
                    "",
                    "Please review the detection file attached."
                ]
                body = "\n".join(body_lines)

                try:
                    email = EmailMessage(
                        subject=subject,
                        body=body,
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                        to=[request.user.email],
                    )

                    # Attach image/video
                    attach_path = None
                    if output_image:
                        filename = os.path.basename(output_image)
                        potential_path = os.path.join(settings.MEDIA_ROOT, filename)
                        if os.path.exists(potential_path):
                            attach_path = potential_path
                    elif output_video:
                        filename = os.path.basename(output_video)
                        potential_path = os.path.join(settings.MEDIA_ROOT, filename)
                        if os.path.exists(potential_path):
                            attach_path = potential_path
                    if attach_path:
                        email.attach_file(attach_path)

                    email.send(fail_silently=False)
                    messages.warning(request, f"⚠️ Weapon detected ({', '.join(found_weapons)}). Message sent to registered mail.")
                except Exception as e:
                    messages.error(request, f"Failed to send alert email: {e}")
            else:
                messages.success(request, "✅ No weapon detected in the uploaded file.")

    else:
       form = UploadMediaForm()

    records = DetectionRecord.objects.filter(
    user=request.user
).order_by('-detected_at')

    total_scans = records.count()
   
    
    

    weapon_alerts = records.count()

    verified_users = EmailOTP.objects.filter(is_verified=True).count()
    
    return render(request, 'detection_app/result.html', {
        'form': form,
        'output_image': output_image,
        'output_video': output_video,
        'records': records,
        'total_scans': total_scans,
        'weapon_alerts': weapon_alerts,
        'verified_users': verified_users,
        
})

# -----------------------------
#  REAL-TIME DETECTION STREAM
# -----------------------------
def gen_frames():
    """Generate frames from webcam in real-time using YOLO detection."""
    global last_alert_time

    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)

    while True:
        success, frame = cap.read()

        if not success:
            break

        results = model.predict(
            source=frame,
            conf=0.5,
            imgsz=640,
            stream=True
        )

        for r in results:
            annotated_frame = r.plot()

            detected_classes = []

            if hasattr(r, "boxes") and len(r.boxes) > 0:
                cls_ids = r.boxes.cls.cpu().numpy().astype(int)

                for cls_id in cls_ids:
                    detected_classes.append(
                        r.names[cls_id].lower()
                    )

            weapon_found = any(
                x in detected_classes
                for x in ["knife", "pistol"]
            )

            # Send only one email every 60 seconds
            if weapon_found and (time.time() - last_alert_time > 60):

                # Save screenshot
                image_path = os.path.join(
                    settings.MEDIA_ROOT,
                    f"weapon_detected_{int(time.time())}.jpg"
                )

                cv2.imwrite(image_path, annotated_frame)

                # Create email with image attachment
                email = EmailMessage(
                    "⚠️ Real-Time Weapon Detection Alert",
                    f"Weapon detected in live camera feed.\n\nDetected: {', '.join(detected_classes)}",
                    settings.EMAIL_HOST_USER,
                    ["projecttworkk36@gmail.com"]  # change if needed
                )

                email.attach_file(image_path)
                email.send(fail_silently=False)

                print("EMAIL WITH IMAGE SENT:", detected_classes)

                last_alert_time = time.time()

        ret, buffer = cv2.imencode('.jpg', annotated_frame)
        frame_bytes = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' +
            frame_bytes +
            b'\r\n'
        )

    cap.release()
def realtime_detection(request):
    return StreamingHttpResponse(
        gen_frames(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )

# -----------------------------
#  USER AUTH
# -----------------------------
def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()

            # Save user info to CSV
            with open(CSV_PATH, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([
                    user.username,
                    user.email,
                    form.cleaned_data['password']
                ])

            otp = str(random.randint(100000, 999999))

            EmailOTP.objects.create(
                user=user,
                otp=otp,
                is_verified=False
            )

            # Save user id in session
            request.session['otp_user_id'] = user.id

            print("Saved Session User ID:", user.id)

            send_mail(
                "Weapon Detection OTP Verification",
                f"Your OTP is: {otp}",
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False
            )

            messages.success(
                request,
                "OTP sent to your email. Please verify."
            )

            return redirect('verify_otp')

    else:
        form = RegisterForm()

    return render(
        request,
        'detection_app/register.html',
        {'form': form}
    )

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)

        if form.is_valid():
            user = authenticate(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password']
            )

            if user:

                try:
                    otp_obj = EmailOTP.objects.get(user=user)

                    if not otp_obj.is_verified:
                        messages.error(
                            request,
                            "Please verify your email first."
                        )
                        return redirect('verify_otp')

                except EmailOTP.DoesNotExist:
                    messages.error(
                        request,
                        "Email verification record not found."
                    )
                    return redirect('login')

                login(request, user)

                messages.success(
                request,
                f"Welcome, {user.username}!"
)

                return redirect('index')

            else:
                messages.error(
                    request,
                    "Invalid credentials."
                )

    else:
        form = LoginForm()

    return render(
        request,
        'detection_app/login.html',
        {'form': form}
    )



def logout_view(request):
    logout(request)
    messages.info(request, "Logged out successfully.")
    return redirect('login')
def verify_otp(request):

    if request.method == "POST":

        entered_otp = request.POST.get("otp")

        user_id = request.session.get("otp_user_id")

        otp_obj = EmailOTP.objects.filter(
            user_id=user_id
        ).first()
        print("Entered OTP:", entered_otp)
        print("Session User ID:", user_id)
        print("Database OTP:", otp_obj.otp if otp_obj else "NOT FOUND")
        if otp_obj and otp_obj.otp == entered_otp:

            otp_obj.is_verified = True
            otp_obj.save()

            messages.success(
                request,
                "Email verified successfully. Please login."
            )

            return redirect('login')

        messages.error(
            request,
            "Invalid OTP"
        )

    return render(
        request,
        "detection_app/verify_otp.html"
    )