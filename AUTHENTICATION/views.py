import logging
from urllib.parse import urlsplit

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views import View
from django.contrib import messages

from django.contrib.auth import get_user_model
from SERVICE_INTERNAL.abstract import _response, is_rate_limited
from SERVICE_INTERNAL.email_single import _try_send_login_email

logger = logging.getLogger(__name__)


def _return_to(request):
    """Return a safe, local path supplied by the guest auth flow."""

    target = (request.POST.get("to") or request.GET.get("to") or "").strip()
    if not target or target.startswith(("//", "/\\")):
        return "/"

    parsed = urlsplit(target)
    if (
        not target.startswith("/")
        or parsed.scheme
        or parsed.netloc
        or not url_has_allowed_host_and_scheme(
            target,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )
    ):
        return "/"
    return target


def _auth_context(request, **context):
    return {"return_to": _return_to(request), **context}


class LoginView(View):
    def get(self, request): 
        # remaining_time, _rate_limit = is_rate_limited(request, timeout_window=60, max_requests=3)
        # if _rate_limit:
        #     messages.error(request, message = f"rate limtit reached {remaining_time}" )
        if request.user.is_authenticated:
            messages.info(request, message=f"Hello {request.user.email}, welcome back.".upper())
            return redirect(_return_to(request))
        return render(request, "auth/login.html", _auth_context(request))
    
    def post(self, request):
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        # rate limting here
        remaining_time, _rate_limit = is_rate_limited(request, timeout_window=15, max_requests=3)
        if _rate_limit:
            error = f"Too Frequent Request, try again in {remaining_time} seconds"
            if is_ajax:
                return _response({"detail": error}, status=429)
            return render(request, 'auth/login.html', _auth_context(request, error=error), status=429)

        email = (request.POST.get("email") or "").strip()
        password = (request.POST.get("password") or "").strip()
        if not email or not password:
            if is_ajax:
                return _response({"detail": "Email and password are required."}, status=400)
            return render(request, "auth/login.html", _auth_context(request, error="Email and password are required."), status=400)
        user = get_user_model().objects.filter(email__iexact = email).first()
        if not user.check_password(password):
            if is_ajax:
                return JsonResponse({'detail': 'Invalid EMail Or PASSWORD'}, status = 400)
            return redirect(return_to)
            
        
        # user = authenticate(request, email=email.upper(), password=password)
        if user is not None and user.is_active:
            _try_send_login_email(user)
            request.session["session_meta"] = {
                "logged_in_at": timezone.now().isoformat(),
                "ip": request.META.get("REMOTE_ADDR", "Unknown IP"),
                "user_agent": request.META.get("HTTP_USER_AGENT", "Unknown device"),
            }
            login(request, user)
            return_to = _return_to(request)
            if is_ajax:
                return _response({"detail": "Login successful.", "redirect_to": return_to}, status=200)
            return redirect(return_to)
        # print(f"xxxxxxxxxxxxxxxxxx --------------- {user.is_active}")
        if user is not None and not user.is_active:
            if is_ajax:
                return _response({"detail": "Account Have Been Suspended."}, status=403)
            return render(request, "auth/login.html", _auth_context(request, error="Account Have Been Suspended."), status=403)
        if is_ajax:
            return _response({"detail": "Invalid email or password."}, status=401)
        return render(request, "auth/login.html", _auth_context(request, error="Invalid email or password."), status=401)


class LogoutView(View):
    def post(self, request):
        info_logger(logger, msg=f"ACCOUNT LOGOUT: {request.user.email} logged out successfully")
        logout(request)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return _response({"detail": "success"}, status=200)
        return redirect("/")


class RegisterView(View):
    def get(self, request):
        if request.user.is_authenticated:
            messages.info(request, message=f"Hello {request.user.email}, welcome back.".upper())
            return redirect(_return_to(request))
        return render(request, "auth/register.html", _auth_context(request))

    def post(self, request):
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        email = (request.POST.get("email") or "").strip()
        password = (request.POST.get("password") or "").strip()
        confirm = (request.POST.get("password_confirm") or "").strip()

        if not email or not password:
            error = "Email and password are required."
        elif "@" not in email:
            error = "Enter a valid email address."
        elif password != confirm:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters long."
        elif get_user_model().objects.filter(email__iexact=email).exists():
            error = "Email Taken OR Email Not Allowed"
        else:
            error = None

        if error is not None:
            if is_ajax:
                return _response({"detail": error}, status=400)
            return render(request, "auth/register.html", _auth_context(request, error=error), status=400)

        user = get_user_model().objects.create_user(email=email, password=password)
        login(request, user)
        return_to = _return_to(request)
        if is_ajax:
            return _response({"detail": "Account created successfully.", "redirect_to": return_to}, status=200)
        return redirect(return_to)
    
from SERVICE_INTERNAL.abstract import info_logger
def csrf_failure(request, exception=None, **args):
    info_logger(msg=f"CSRF_ERROR: {request.user or 'Anonymous user'} tried to perform some action but experienced CSRF error")
    # return JsonResponse({'detail': 'csrf error'}, status = 403)
    return render(request, "csrf_fail.html", status=403)
