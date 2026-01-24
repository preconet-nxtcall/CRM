# app/routes/admin_call_analytics.py

from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy import func, case
from app.models import db, User, CallHistory
from datetime import datetime, timedelta
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

bp = Blueprint("admin_call_analytics", __name__, url_prefix="/api/admin/call-analytics")


def is_admin():
    return get_jwt().get("role") == "admin"


@bp.route("", methods=["GET"])
@jwt_required()
def admin_analytics_all_users():
    """
    Returns aggregated analytics for ALL users under the admin.
    Supports filtering by period: 'today', 'month', 'all' (default).
    NOTE: The user requested 'today' and 'monthly' filters.
    """
    if not is_admin():
        return jsonify({"error": "Admin access required"}), 403

    try:
        admin_id = int(get_jwt_identity())

        # Get users under admin
        users = User.query.filter_by(admin_id=admin_id).all()
        user_ids = [u.id for u in users]

        if not user_ids:
            return jsonify({
                "total_calls": 0,
                "incoming": 0,
                "outgoing": 0,
                "missed": 0,
                "rejected": 0,
                "daily_trend": [],
                "user_summary": []
            }), 200

        # --- DATE FILTER LOGIC ---
        period = request.args.get("period", "all") # default all to match previous behavior if not specified
        
        # Date Filter Logic (Dynamic Timezone)
        now_utc = datetime.utcnow()
        try:
             offset_min = int(request.args.get("timezone_offset", 0))
             # If 0, maybe default to IST? Let's respect 0 (UTC) if sent, but default to IST if not?
             # Actually, if frontend sends 0, it means UTC. 
             # Let's fallback to IST only if NOT in args? 
             # The previous code hardcoded IST.
             # If we want to be safe: use offset if valid, else IST.
        except:
             offset_min = -330 # Default to IST (-330 mins offset from UTC)

        # JS getTimezoneOffset() returns +ve if West, -ve if East (opposite of UTC offset usually)
        # IST is UTC+5:30. JS returns -330.
        # So Local = UTC - (-330) = UTC + 330 mins = UTC + 5.5h.
        
        local_delta = timedelta(minutes=-offset_min) 
        # Safety: if offset is 0, local_delta is 0 (UTC).
        # If offset is -330 (IST), local_delta is +330 mins.
        
        now_local = now_utc + local_delta
        today_start_local = datetime(now_local.year, now_local.month, now_local.day)
        
        # Convert back to UTC for DB
        # UTC = Local - delta
        start_date = None
        end_date = None

        if period == "today":
            start_date = today_start_local - local_delta
            end_date = start_date + timedelta(days=1)
        elif period == "month":
            month_start_local = datetime(now_local.year, now_local.month, 1)
            start_date = month_start_local - local_delta
            
            if now_local.month == 12:
                next_month_local = datetime(now_local.year + 1, 1, 1)
            else:
                next_month_local = datetime(now_local.year, now_local.month + 1, 1)
            
            end_date = next_month_local - local_delta
        
        # If period is 'all' or unknown, we don't apply date filters to the MAIN counts if that was the original intent,
        # BUT the task says "show only today data" etc.
        # So we should apply filters.
        
        # Base query for CallHistory
        base_query = CallHistory.query.filter(CallHistory.user_id.in_(user_ids))
        if start_date:
            base_query = base_query.filter(CallHistory.timestamp >= start_date)
        if end_date:
            base_query = base_query.filter(CallHistory.timestamp < end_date)

        # Helper to execute count queries on the filtered base
        def get_count(filter_condition=None):
            q = base_query
            if filter_condition is not None:
                q = q.filter(filter_condition)
            return db.session.query(func.count(q.statement.columns.id)).scalar() or 0

        def get_sum(col):
            return db.session.query(func.sum(col)).filter(
                col.expression.left.in_(user_ids)
            ).filter(
                CallHistory.timestamp >= start_date if start_date else True,
                CallHistory.timestamp < end_date if end_date else True
            ).scalar() or 0
            
        # Optimization: Single aggregation query is better, but keeping style consistent with previous code for safety
        # unless it was too slow. Previous code Aggregated independently.
        # Let's use the base_query efficiently.
        
        # We can actually do one big query for the totals
        totals = db.session.query(
            func.count(CallHistory.id),
            func.sum(case((func.lower(CallHistory.call_type) == "incoming", 1), else_=0)),
            func.sum(case((func.lower(CallHistory.call_type) == "outgoing", 1), else_=0)),
            func.sum(case((func.lower(CallHistory.call_type) == "missed", 1), else_=0)),
            func.sum(case((func.lower(CallHistory.call_type) == "rejected", 1), else_=0)),
            func.sum(CallHistory.duration),
             # averages
            func.avg(case((func.lower(CallHistory.call_type) == "incoming", CallHistory.duration), else_=None)),
            func.avg(case((func.lower(CallHistory.call_type) == "outgoing", CallHistory.duration), else_=None)),
            func.count(func.distinct(CallHistory.phone_number))
        ).filter(
            CallHistory.user_id.in_(user_ids)
        )
        
        if start_date:
            totals = totals.filter(CallHistory.timestamp >= start_date)
        if end_date:
            totals = totals.filter(CallHistory.timestamp < end_date)
            
        (
            total_calls, 
            incoming, 
            outgoing, 
            missed, 
            rejected, 
            total_duration,
            avg_in_dur,
            avg_out_dur,
            unique_numbers
        ) = totals.first()
        
        # Handle None
        total_calls = total_calls or 0
        incoming = int(incoming or 0)
        outgoing = int(outgoing or 0)
        missed = int(missed or 0)
        rejected = int(rejected or 0)
        total_duration = int(total_duration or 0)
        avg_inbound_duration = float(avg_in_dur or 0)
        avg_outbound_duration = float(avg_out_dur or 0)
        unique_numbers = unique_numbers or 0
        
        total_answered = incoming + outgoing

        # ---------- Daily trend (last 7 days) ----------
        # Trend should usually show context, maybe keep it last 7 days regardless of filter?
        # Or filter it? Usually trend charts are specific.
        # existing logic: 7 days. Let's keep existing logic for the chart for now unless 'today' only makes sense to show activity per hour?
        # The frontend hides the chart anyway in the provided code snippets (commented out), but let's leave it as is.
        
        week_ago = datetime.utcnow() - timedelta(days=7)

        # Activity Trend (Count)
        trend_rows = (
            db.session.query(
                func.date(CallHistory.timestamp).label("date"),
                func.count(CallHistory.id).label("count"),
                func.sum(CallHistory.duration).label("duration")
            )
            .filter(CallHistory.user_id.in_(user_ids), CallHistory.timestamp >= week_ago)
            .group_by(func.date(CallHistory.timestamp))
            .order_by(func.date(CallHistory.timestamp))
            .all()
        )

        trend_map = {str(r.date): {"count": int(r.count), "duration": int(r.duration or 0)} for r in trend_rows}

        daily_trend = []
        duration_trend = []
        
        for i in range(7, 0, -1):
            d = (datetime.utcnow() - timedelta(days=i - 1)).date()
            d_str = str(d)
            data = trend_map.get(d_str, {"count": 0, "duration": 0})
            
            daily_trend.append({
                "date": d_str,
                "count": data["count"]
            })
            duration_trend.append({
                "date": d_str,
                "duration": data["duration"]
            })

        # ---------- User summary (Filtered) ----------
        # Need to apply the same date filters to the user summary
        
        # ---------- User summary (Filtered) ----------
        # Need to apply the same date filters to the user summary
        
        # Base selection columns
        summary_cols = [
            User.id.label("user_id"),
            User.name.label("user_name"),

            func.coalesce(func.sum(
                case((func.lower(CallHistory.call_type) == "incoming", 1), else_=0)
            ), 0).label("incoming"),

            func.coalesce(func.sum(
                case((func.lower(CallHistory.call_type) == "outgoing", 1), else_=0)
            ), 0).label("outgoing"),

            func.coalesce(func.sum(
                case((func.lower(CallHistory.call_type) == "missed", 1), else_=0)
            ), 0).label("missed"),

            func.coalesce(func.sum(
                case((func.lower(CallHistory.call_type) == "rejected", 1), else_=0)
            ), 0).label("rejected"),

            func.coalesce(func.sum(CallHistory.duration), 0).label("total_duration_seconds"),

            User.last_sync.label("last_sync")
        ]
        
        if start_date:
             # If filtering by date, apply filter ON the join condition for correct outer join behavior
             # (Users with no calls in range should still appear with 0s)
             summary_query = db.session.query(*summary_cols).select_from(User).outerjoin(CallHistory, 
                (User.id == CallHistory.user_id) & 
                (CallHistory.timestamp >= start_date if start_date else True) &
                (CallHistory.timestamp < end_date if end_date else True)
            )
        else:
            # No date filter, simple outer join
            summary_query = db.session.query(*summary_cols).select_from(User).outerjoin(CallHistory, User.id == CallHistory.user_id)

        summary_rows = summary_query.filter(User.admin_id == admin_id)\
            .group_by(User.id)\
            .order_by(User.name)\
            .all()

        user_summary = []
        for r in summary_rows:
            user_summary.append({
                "user_id": int(r.user_id),
                "user_name": r.user_name,
                "incoming": int(r.incoming or 0),
                "outgoing": int(r.outgoing or 0),
                "missed": int(r.missed or 0),
                "rejected": int(r.rejected or 0),
                "total_duration_seconds": int(r.total_duration_seconds or 0),
                "last_sync": (r.last_sync.isoformat() + 'Z') if r.last_sync else None
            })

        # ---------- Final response ----------
        return jsonify({
            "total_calls": int(total_calls),
            "total_duration": int(total_duration),
            "incoming": int(incoming),
            "outgoing": int(outgoing),
            "missed": int(missed),
            "rejected": int(rejected),
            "total_answered": int(total_answered),
            "unique_numbers": int(unique_numbers),
            "avg_inbound_duration": int(avg_inbound_duration),
            "avg_outbound_duration": int(avg_outbound_duration),
            "daily_trend": daily_trend,
            "duration_trend": duration_trend,
            "user_summary": user_summary,
            "period": period
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400


@bp.route("/download-report", methods=["GET"])
@jwt_required()
def download_analytics_report():
    """
    Generates and downloads a PDF report for the filtered data.
    """
    if not is_admin():
        return jsonify({"error": "Admin access required"}), 403
    
    if not HAS_REPORTLAB:
        return jsonify({"error": "PDF generation library (reportlab) not installed on server."}), 500

    try:
        admin_id = int(get_jwt_identity())
        
        # --- 1. Fetch Data (Same logic as analytics endpoint effectively) ---
        period = request.args.get("period", "all")
        
        now_utc = datetime.utcnow()
        ist_offset = timedelta(hours=5, minutes=30)
        now_ist = now_utc + ist_offset
        today_start_ist = datetime(now_ist.year, now_ist.month, now_ist.day)

        start_date = None
        end_date = None
        period_label = "All Time"

        if period == "today":
            start_date = today_start_ist - ist_offset
            end_date = start_date + timedelta(days=1)
            period_label = f"Today ({now_ist.strftime('%d %b %Y')})"
        elif period == "month":
            month_start_ist = datetime(now_ist.year, now_ist.month, 1)
            start_date = month_start_ist - ist_offset
            
            if now_ist.month == 12:
                next_month_ist = datetime(now_ist.year + 1, 1, 1)
            else:
                next_month_ist = datetime(now_ist.year, now_ist.month + 1, 1)
                
            end_date = next_month_ist - ist_offset
            period_label = f"Monthly ({now_ist.strftime('%B %Y')})"
            
        # Query User Summary
        # Query User Summary
        # Base columns
        summary_cols = [
            User.id,
            User.name,
            func.sum(case((func.lower(CallHistory.call_type) == "incoming", 1), else_=0)).label("incoming"),
            func.sum(case((func.lower(CallHistory.call_type) == "outgoing", 1), else_=0)).label("outgoing"),
            func.sum(case((func.lower(CallHistory.call_type) == "missed", 1), else_=0)).label("missed"),
            func.sum(case((func.lower(CallHistory.call_type) == "rejected", 1), else_=0)).label("rejected"),
            func.coalesce(func.sum(CallHistory.duration), 0).label("total_duration"),
            User.last_sync
        ]

        if start_date:
            summary_query = db.session.query(*summary_cols).select_from(User).outerjoin(CallHistory, 
                (User.id == CallHistory.user_id) & 
                (CallHistory.timestamp >= start_date) &
                (CallHistory.timestamp < end_date)
            )
        else:
            summary_query = db.session.query(*summary_cols).select_from(User).outerjoin(CallHistory, 
                User.id == CallHistory.user_id
            )

        summary_rows = summary_query.filter(User.admin_id == admin_id)\
            .group_by(User.id)\
            .order_by(User.name)\
            .all()

        # --- 2. Generate PDF ---
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=24,
            alignment=TA_CENTER,
            spaceAfter=10,
            textColor=colors.HexColor('#2563EB')
        )
        elements.append(Paragraph("NxtCall.app", title_style))
        
        # Subtitle
        subtitle_style = ParagraphStyle(
            'SubtitleStyle',
            parent=styles['Heading2'],
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=30,
            textColor=colors.gray
        )
        elements.append(Paragraph(f"User Performance Report - {period_label}", subtitle_style))

        # Table Data
        # Headers
        table_data = [[
            "User", "Incoming", "Outgoing", "Missed", "Rejected", "Duration", "Last Sync"
        ]]
        
        def fmt_dur(seconds):
            if not seconds: return "0s"
            h = seconds // 3600
            m = (seconds % 3600) // 60
            s = seconds % 60
            parts = []
            if h: parts.append(f"{h}h")
            if m: parts.append(f"{m}m")
            if s: parts.append(f"{s}s")
            return " ".join(parts[:2]) if len(parts) > 2 else " ".join(parts)

        for r in summary_rows:
            last_sync_str = r.last_sync.strftime('%Y-%m-%d') if r.last_sync else "Never"
            table_data.append([
                r.name,
                str(int(r.incoming or 0)),
                str(int(r.outgoing or 0)),
                str(int(r.missed or 0)),
                str(int(r.rejected or 0)),
                fmt_dur(int(r.total_duration or 0)),
                last_sync_str
            ])

        if len(table_data) == 1:
            elements.append(Paragraph("No data available for this period.", styles['Normal']))
        else:
            # Table Style
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                 # Align name left
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')])
            ]))
            elements.append(t)
        
        # Build
        doc.build(elements)
        buffer.seek(0)
        
        filename = f"NxtCall_Report_{period}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400


@bp.route("/<int:user_id>", methods=["GET"])
@jwt_required()
def admin_analytics_single_user(user_id):
    """
    Returns analytics for a SINGLE user for a specific period (default: today).
    """
    if not is_admin():
        return jsonify({"error": "Admin access required"}), 403

    try:
        admin_id = int(get_jwt_identity())

        # Verify user belongs to admin
        user = User.query.filter_by(id=user_id, admin_id=admin_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Determine date range (default: today)
        # Determine date range (default: today) using IST
        period = request.args.get("period", "today")
        now_utc = datetime.utcnow()
        ist_offset = timedelta(hours=5, minutes=30)
        now_ist = now_utc + ist_offset
        today_start_ist = datetime(now_ist.year, now_ist.month, now_ist.day)
        
        if period == "today":
            start_dt = today_start_ist - ist_offset
            end_dt = start_dt + timedelta(days=1)
        elif period == "week":
            # Week ending today
            start_dt = (today_start_ist - ist_offset) - timedelta(days=7)
            end_dt = (today_start_ist - ist_offset) + timedelta(days=1)
        elif period == "month":
            month_start_ist = datetime(now_ist.year, now_ist.month, 1)
            start_dt = month_start_ist - ist_offset
            if now_ist.month == 12:
                next_month_ist = datetime(now_ist.year + 1, 1, 1)
            else:
                next_month_ist = datetime(now_ist.year, now_ist.month + 1, 1)
            end_dt = next_month_ist - ist_offset
        elif period == "all":
            start_dt = datetime.min
            end_dt = datetime.max
        else:
            # Fallback to today if unknown
            start_dt = datetime(now.year, now.month, now.day)
            end_dt = start_dt + timedelta(days=1)

        # Query stats
        stats = db.session.query(
            func.count(CallHistory.id).label("total"),
            func.sum(case((func.lower(CallHistory.call_type) == "incoming", 1), else_=0)).label("incoming"),
            func.sum(case((func.lower(CallHistory.call_type) == "outgoing", 1), else_=0)).label("outgoing"),
            func.sum(case((func.lower(CallHistory.call_type) == "missed", 1), else_=0)).label("missed"),
            func.sum(case((func.lower(CallHistory.call_type) == "rejected", 1), else_=0)).label("rejected"),
            func.sum(CallHistory.duration).label("duration")
        ).filter(
            CallHistory.user_id == user_id,
            CallHistory.timestamp >= start_dt,
            CallHistory.timestamp < end_dt
        ).first()

        return jsonify({
            "user_name": user.name,
            "period": period,
            "total_calls": int(stats.total or 0),
            "incoming": int(stats.incoming or 0),
            "outgoing": int(stats.outgoing or 0),
            "missed": int(stats.missed or 0),
            "rejected": int(stats.rejected or 0),
            "total_duration_seconds": int(stats.duration or 0)
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400
