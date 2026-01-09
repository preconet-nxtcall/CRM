# app/routes/admin_call_history.py

from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timedelta
from app.models import db, User, CallHistory
from sqlalchemy import or_, func, case
import io

# Optional: ReportLab for PDF
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

bp = Blueprint("admin_all_call_history", __name__, url_prefix="/api/admin")


from functools import wraps

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if get_jwt().get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper


@bp.route("/all-call-history", methods=["GET"])
@jwt_required()
@admin_required
def all_call_history():
    try:
        admin_id = int(get_jwt_identity())

        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 30))

        # ============================
        # 1️⃣ DATE FILTER
        # ============================
        filter_type = request.args.get("filter")  # today / week / month
        custom_date = request.args.get("date", "").strip()  # YYYY-MM-DD format
        
        now = datetime.utcnow()
        start_time = None

        if filter_type == "today":
            start_time = datetime(now.year, now.month, now.day)
        elif filter_type == "week":
            start_time = now - timedelta(days=7)
        elif filter_type == "month":
            # Change "Month" to "Start of Current Month"
            start_time = datetime(now.year, now.month, 1)
        # Removed automatic 7-day default to show all available data
        # Users can explicitly apply filters if needed

        # ============================
        # 2️⃣ PHONE SEARCH FILTER
        # ============================
        search = request.args.get("search")
        
        # ============================
        # 3️⃣ CALL TYPE FILTER
        # ============================
        call_type = request.args.get("call_type")  # incoming/outgoing/missed

        # ============================
        # 4️⃣ USER FILTER
        # ============================
        user_id = request.args.get("user_id")
        if user_id and user_id != "all":
            try:
                user_id = int(user_id)
            except ValueError:
                user_id = None
        else:
            user_id = None

        # ============================
        # 6️⃣ BASE QUERY (JOIN + ADMIN FILTER)
        # ============================
        query = (
            db.session.query(CallHistory, User)
            .join(User, CallHistory.user_id == User.id)
            .filter(User.admin_id == admin_id)
        )

        # Apply date filter
        if custom_date:
            try:
                # Use explicit string range for maximum compatibility
                # This ensures we cover the entire day regardless of object types
                start_date_str = f"{custom_date} 00:00:00"
                end_date_str = f"{custom_date} 23:59:59"
                query = query.filter(CallHistory.timestamp >= start_date_str, CallHistory.timestamp <= end_date_str)
            except Exception:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        # New Month Filter (YYYY-MM)
        month_param = request.args.get("month")
        if month_param:
            try:
                # Parse YYYY-MM
                part_year, part_month = map(int, month_param.split('-'))
                
                # Start of month
                start_dt = datetime(part_year, part_month, 1)
                
                # End of month (start of next month)
                if part_month == 12:
                    end_dt = datetime(part_year + 1, 1, 1)
                else:
                    end_dt = datetime(part_year, part_month + 1, 1)
                
                query = query.filter(CallHistory.timestamp >= start_dt, CallHistory.timestamp < end_dt)
            except ValueError:
                return jsonify({"error": "Invalid month format. Use YYYY-MM"}), 400

        elif start_time:
            query = query.filter(CallHistory.timestamp >= start_time)

        # Apply phone number search
        if search:
            search_term = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    CallHistory.phone_number.ilike(search_term),
                    CallHistory.formatted_number.ilike(search_term),
                    func.lower(CallHistory.contact_name).like(search_term)
                )
            )

        # Apply call type filter
        if call_type:
            query = query.filter(func.lower(CallHistory.call_type) == call_type.lower())

        # Apply user filter
        if user_id:
            query = query.filter(CallHistory.user_id == user_id)

        # Sorting
        query = query.order_by(CallHistory.timestamp.desc())

        # Pagination
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        data = []
        for rec, user_obj in paginated.items:
            # Safely get recording_path (may not exist in DB yet)
            try:
                recording_path = rec.recording_path
            except AttributeError:
                recording_path = None
            
            data.append({
                "id": rec.id,
                "user_id": rec.user_id,
                "user_name": user_obj.name,
                "phone_number": rec.phone_number,
                "formatted_number": rec.formatted_number,
                "contact_name": rec.contact_name,
                "call_type": rec.call_type,
                "duration": rec.duration,
                "recording_path": recording_path,
                "timestamp": rec.timestamp.isoformat() + 'Z' if rec.timestamp else None,
                "created_at": rec.created_at.isoformat() + 'Z' if rec.created_at else None,
            })

        # Calculate Stats for the response if filtered by "today" (or generally if possible)
        # We need "last active day" stats logic if filter is ALL, or "specific day" stats if filter is TODAY.
        stats_response = None
        
        # Only calculate stats if user_id is provided
        if user_id:
            # We need to import Attendance to check work time
            from app.models import Attendance
            
            # Decide which day to show stats for:
            # If "today", show Today'sstats.
            # If "all" or others, show "Last Active Day" stats (like performance page).
            
            target_date = None
            if filter_type == "today":
                target_date = datetime(now.year, now.month, now.day).date()
            else:
                # If not today, we might want "Last Active Day" from the QUERY results? 
                # Or just standard "Last Active Day" of the user?
                # The performance page shows "Last Active Day". Let's replicate that if filter is NOT today.
                # If filter IS today, we explicitly want Today's stats even if 0.
                pass

            # Query Attendance
            att_query = Attendance.query.filter_by(user_id=user_id)
            
            if target_date:
                # Specific day
                att_record = att_query.filter(func.date(Attendance.check_in) == target_date).first()
            else:
                # Last active day (order by date desc)
                att_record = att_query.order_by(Attendance.check_in.desc()).first()

            if att_record:
                # Calculate Duration
                # We need a helper for hms, let's define it inline or import?
                # Inline is safe.
                def fmt_hms_local(seconds):
                    if not seconds: return "0s"
                    h = int(seconds // 3600)
                    m = int((seconds % 3600) // 60)
                    s = int(seconds % 60)
                    parts = []
                    if h: parts.append(f"{h}h")
                    if m: parts.append(f"{m}m")
                    if s: parts.append(f"{s}s")
                    return " ".join(parts)
                
                # Check In / Out
                c_in = att_record.check_in
                c_out = att_record.check_out
                
                # Determine "effective end time" for calculation
                # If active (no checkout), use NOW
                calc_end_time = c_out if c_out else datetime.utcnow()

                # Work Time
                w_time = 0
                if c_in:
                    w_time = (calc_end_time - c_in).total_seconds()
                
                # Calculate Active/Inactive times by analyzing call gaps
                # Get calls for this specific day/filter
                calls_query = CallHistory.query.filter_by(user_id=user_id)
                
                # Apply same date filter as main query
                if filter_type == "today":
                    calls_query = calls_query.filter(CallHistory.timestamp >= start_time)
                elif filter_type == "month":
                    # Use same month logic as main query
                    if now.month == 12:
                        end_time_calc = datetime(now.year + 1, 1, 1)
                    else:
                        end_time_calc = datetime(now.year, now.month + 1, 1)
                    calls_query = calls_query.filter(CallHistory.timestamp >= start_time, CallHistory.timestamp < end_time_calc)
                elif start_time:
                    calls_query = calls_query.filter(CallHistory.timestamp >= start_time)
                
                # Get calls within work session
                # If no c_out, we limit only by c_in
                if c_out:
                    day_calls = calls_query.filter(
                        CallHistory.timestamp >= c_in,
                        CallHistory.timestamp <= c_out
                    ).order_by(CallHistory.timestamp.asc()).all()
                else:
                    day_calls = calls_query.filter(
                        CallHistory.timestamp >= c_in
                    ).order_by(CallHistory.timestamp.asc()).all()
                
                # Calculate active/inactive time
                active_sec = 0
                inactive_sec = 0
                last_sync = c_in
                
                if not last_sync:
                     # Safety fallback if c_in misses
                     last_sync = datetime.utcnow()

                def is_lunch_hour(dt):
                    return dt.hour == 13
                
                for call in day_calls:
                    curr_time = call.timestamp
                    
                    # Skip if in lunch hour
                    if is_lunch_hour(curr_time):
                        last_sync = curr_time
                        continue
                    
                    # Calculate gap
                    raw_gap = (curr_time - last_sync).total_seconds()
                    
                    # Subtract lunch overlap from gap
                    lunch_start = c_in.replace(hour=13, minute=0, second=0, microsecond=0)
                    lunch_end = c_in.replace(hour=14, minute=0, second=0, microsecond=0)
                    
                    overlap_start = max(last_sync, lunch_start)
                    overlap_end = min(curr_time, lunch_end)
                    overlap = max(0, (overlap_end - overlap_start).total_seconds())
                    
                    effective_gap = max(0, raw_gap - overlap)
                    
                    # Classify gap: ≤10 min = active, >10 min = inactive
                    if effective_gap <= 600:
                        active_sec += effective_gap
                    else:
                        inactive_sec += effective_gap
                    
                    last_sync = curr_time
                
                # Final gap from last call to checkout/now
                if day_calls or c_in:
                    final_gap = (calc_end_time - last_sync).total_seconds()
                    
                    lunch_start = c_in.replace(hour=13, minute=0, second=0, microsecond=0)
                    lunch_end = c_in.replace(hour=14, minute=0, second=0, microsecond=0)
                    
                    overlap_start = max(last_sync, lunch_start)
                    overlap_end = min(calc_end_time, lunch_end)
                    overlap = max(0, (overlap_end - overlap_start).total_seconds())
                    
                    effective_gap = max(0, final_gap - overlap)
                    
                    if effective_gap <= 600:
                        active_sec += effective_gap
                    else:
                        inactive_sec += effective_gap
                
                stats_response = {
                    "details": {
                        "check_in": c_in.isoformat() + 'Z' if c_in else None,
                        "check_out": c_out.isoformat() + 'Z' if c_out else None,
                        "work_time": fmt_hms_local(w_time),
                        "active_time": fmt_hms_local(active_sec),
                        "inactive_time": fmt_hms_local(inactive_sec)
                    }
                }

        return jsonify({
            "call_history": data,
            "meta": {
                "page": paginated.page,
                "per_page": paginated.per_page,
                "total": paginated.total,
                "pages": paginated.pages,
                "has_next": paginated.has_next,
                "has_prev": paginated.has_prev,
            },
            "stats": stats_response
        }), 200

    except Exception as e:
        return jsonify({"error": "Internal error", "detail": str(e)}), 400


@bp.route("/download-user-history", methods=["GET"])
@jwt_required()
@admin_required
def download_user_history():
    """
    Generates and downloads a PDF report for a single user's call history.
    Values passed: user_id, filter (today, month, all)
    """
    if not HAS_REPORTLAB:
        return jsonify({"error": "PDF generation library (reportlab) not installed on server."}), 500

    try:
        admin_id = int(get_jwt_identity())
        user_id = request.args.get("user_id")
        
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        # Verify user exists and belongs to admin
        user = User.query.filter_by(id=user_id, admin_id=admin_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        # ============================
        # 1️⃣ DATE FILTER SETUP
        # ============================
        filter_type = request.args.get("filter", "all")
        now = datetime.utcnow()
        start_time = None
        period_label = "All Time"

        if filter_type == "today":
            start_time = datetime(now.year, now.month, now.day)
            period_label = f"Today ({now.strftime('%d %b %Y')})"
        elif filter_type == "month":
            start_time = datetime(now.year, now.month, 1) # Start of current month
            period_label = f"Monthly ({now.strftime('%B %Y')})"
        
        # ============================
        # 2️⃣ QUERY DATA
        # ============================
        query = CallHistory.query.filter_by(user_id=user_id)
        
        if start_time:
            # For "month", we ideally want the whole month range, but the previous logic just used start_time >= X
            # Let's improve it for month to be cleaner
            if filter_type == "month":
                 if now.month == 12:
                     end_time = datetime(now.year + 1, 1, 1)
                 else:
                     end_time = datetime(now.year, now.month + 1, 1)
                 query = query.filter(CallHistory.timestamp >= start_time, CallHistory.timestamp < end_time)
            else:
                 query = query.filter(CallHistory.timestamp >= start_time)
        
        # Sort by latest
        calls = query.order_by(CallHistory.timestamp.desc()).all()

        # ============================
        # 3️⃣ GENERATE PDF
        # ============================
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=5,
            textColor=colors.HexColor('#2563EB')
        )
        elements.append(Paragraph("NxtCall.app", title_style))
        
        # Subtitle
        subtitle_style = ParagraphStyle(
            'SubtitleStyle',
            parent=styles['Normal'],
            fontSize=12,
            alignment=TA_CENTER,
            spaceAfter=20,
            textColor=colors.gray
        )
        elements.append(Paragraph(f"Report Period: {period_label}", subtitle_style))

        # Table Data
        # Columns: Type, Number, Duration, Date
        table_data = [[ "Type", "Number", "Duration", "Date & Time" ]]

        def fmt_dur(seconds):
             if not seconds: return "0s"
             h = seconds // 3600
             m = (seconds % 3600) // 60
             s = seconds % 60
             parts = []
             if h: parts.append(f"{h}h")
             if m: parts.append(f"{m}m")
             if s: parts.append(f"{s}s")
             return " ".join(parts)

        for c in calls:
            # Color coding for type (text only in PDF)
            c_type = c.call_type.capitalize()
            
            table_data.append([
                c_type,
                c.phone_number,
                fmt_dur(c.duration),
                c.timestamp.strftime('%Y-%m-%d %H:%M:%S') if c.timestamp else "-"
            ])

        if len(table_data) == 1:
            elements.append(Paragraph("No calls found for this period.", styles['Normal']))
        else:
            t = Table(table_data, colWidths=[80, 150, 80, 150])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            elements.append(t)

        doc.build(elements)
        buffer.seek(0)
        
        filename = f"CallHistory_{user.name}_{filter_type}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal error generating report", "detail": str(e)}), 400