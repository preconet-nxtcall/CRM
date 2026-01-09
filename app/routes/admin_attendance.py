from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timedelta
from sqlalchemy import func
from io import BytesIO
from flask import send_file
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from ..models import db, Admin, Attendance, User

bp = Blueprint("admin_attendance", __name__, url_prefix="/api/admin/attendance")

def admin_required():
    claims = get_jwt()
    return claims.get("role") == "admin"


@bp.route("", methods=["GET"])
@jwt_required()
def get_admin_attendance():
    """Return FULL attendance data for admin dashboard."""
    
    # Must be admin
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    try:
        admin_id = int(get_jwt_identity())
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    # Admin exists?
    admin = Admin.query.get(admin_id)
    if not admin:
        return jsonify({"attendance": [], "meta": {}}), 200

    # Date Filter (YYYY-MM-DD)
    date_str = request.args.get("date")
    
    start_time = None
    end_time = None

    if date_str:
        try:
            # Use explicit string range for maximum compatibility
            start_time = f"{date_str} 00:00:00"
            end_time = f"{date_str} 23:59:59"
        except Exception as e:
            current_app.logger.warning(f"Invalid date format: {date_str} - {e}")
            return jsonify({"error": "Invalid date format"}), 400
    
    # Month Filter (YYYY-MM)
    month_param = request.args.get("month")
    if month_param:
        try:
            part_year, part_month = map(int, month_param.split('-'))
            start_time = datetime(part_year, part_month, 1)
            if part_month == 12:
                end_time = datetime(part_year + 1, 1, 1)
            else:
                end_time = datetime(part_year, part_month + 1, 1)
        except ValueError:
            return jsonify({"error": "Invalid month format. Use YYYY-MM"}), 400

    # Pagination
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 25))
    except ValueError:
        page = 1
        per_page = 25

    try:
        # Query all users of this admin
        # Explicit join to avoid ambiguity
        base_query = db.session.query(Attendance).join(User, Attendance.user_id == User.id).filter(User.admin_id == admin_id)

        # User Filter (ADDED)
        user_id = request.args.get("user_id")
        if user_id and user_id != "all":
            try:
                base_query = base_query.filter(Attendance.user_id == int(user_id))
            except ValueError:
                pass

        if start_time and end_time:
            # Note: For strict day filter we used inclusive end_time (23:59:59).
            # For month filter we calculated start of NEXT month, so use < for end_time.
            # But wait, date filter set end_time to 23:59:59.
            # Let's standardize.
            
            if month_param:
                 base_query = base_query.filter(Attendance.check_in >= start_time, Attendance.check_in < end_time)
            else:
                 # Standard date filter
                 base_query = base_query.filter(Attendance.check_in >= start_time, Attendance.check_in <= end_time)


        paginated = base_query.order_by(Attendance.check_in.desc()).paginate(page=page, per_page=per_page, error_out=False)

        results = []
        for a in paginated.items:
            results.append({
                "id": a.id,
                "user_id": a.user_id,
                "user_name": a.user.name if a.user else "Unknown",
                "status": a.status,
                "check_in": a.check_in.isoformat() + 'Z' if a.check_in else None,
                "check_out": a.check_out.isoformat() + 'Z' if a.check_out else None,
                "address": a.address,
                "latitude": a.latitude,
                "longitude": a.longitude,
                "image_path": a.image_path,
                # ✅ ADD CHECKOUT FIELDS
                "check_out_address": a.check_out_address,
                "check_out_latitude": a.check_out_latitude,
                "check_out_longitude": a.check_out_longitude,
                "check_out_image": a.check_out_image,
                "synced": a.synced,
                "external_id": a.external_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "sync_timestamp": a.sync_timestamp.isoformat() if a.sync_timestamp else None
            })

        return jsonify({
            "attendance": results,
            "meta": {
                "page": paginated.page,
                "per_page": paginated.per_page,
                "total": paginated.total,
                "pages": paginated.pages,
                "has_next": paginated.has_next,
                "has_prev": paginated.has_prev
            }
        }), 200

    except Exception as e:
        current_app.logger.exception("Admin attendance query failed")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/export_pdf", methods=["GET"])
@jwt_required()
def export_attendance_pdf():
    """Export attendance data as PDF."""
    
    if not admin_required():
        return jsonify({"error": "Admin access only"}), 403

    try:
        admin_id = int(get_jwt_identity())
        
        # Build Query (Reuse logic)
        base_query = db.session.query(Attendance).join(User, Attendance.user_id == User.id).filter(User.admin_id == admin_id)

        # Filters
        date_str = request.args.get("date")
        month_param = request.args.get("month")
        user_id = request.args.get("user_id")

        start_time = None
        end_time = None

        if date_str:
            try:
                start_time = f"{date_str} 00:00:00"
                end_time = f"{date_str} 23:59:59"
            except Exception:
                pass
        
        if month_param:
            try:
                part_year, part_month = map(int, month_param.split('-'))
                start_time = datetime(part_year, part_month, 1)
                if part_month == 12:
                    end_time = datetime(part_year + 1, 1, 1)
                else:
                    end_time = datetime(part_year, part_month + 1, 1)
            except ValueError:
                pass

        if user_id and user_id != "all":
            try:
                base_query = base_query.filter(Attendance.user_id == int(user_id))
            except ValueError:
                pass

        if start_time and end_time:
            if month_param:
                 base_query = base_query.filter(Attendance.check_in >= start_time, Attendance.check_in < end_time)
            else:
                 base_query = base_query.filter(Attendance.check_in >= start_time, Attendance.check_in <= end_time)

        # Get all records for export
        records = base_query.order_by(Attendance.check_in.desc()).all()

        # PDF GENERATION
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph("Nxt Call.app", styles['Title']))
        elements.append(Spacer(1, 12))
        
        # Table Data
        # User Name, Check In Time, Check In Address, Check Out Time, Status, Check Out Address
        data = [["User Name", "Check In Time", "Check In Address", "Check Out Time", "Status", "Check Out Address"]]
        
        for r in records:
            c_in = r.check_in.strftime("%Y-%m-%d %H:%M") if r.check_in else "-"
            c_out = r.check_out.strftime("%Y-%m-%d %H:%M") if r.check_out else "-"
            user_name = r.user.name if r.user else "Unknown"
            
            # Wrapper for address to allow line breaks
            addr_in_style = styles['Normal']
            addr_in_style.fontSize = 8
            
            addr_in = r.address or "-"
            addr_in_para = Paragraph(addr_in, addr_in_style)

            addr_out = r.check_out_address or "-"
            addr_out_para = Paragraph(addr_out, addr_in_style)
                
            data.append([
                user_name,
                c_in,
                addr_in_para,
                c_out,
                r.status,
                addr_out_para
            ])

        # Table Style
        if len(data) == 1:
            elements.append(Paragraph("No records found.", styles['Normal']))
        else:
            # Table Style matching Call History
            # Columns: User(60), In Time(80), In Addr(100), Out Time(80), Status(50), Out Addr(100)
            col_widths = [60, 80, 100, 80, 50, 100]
            table = Table(data, colWidths=col_widths)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(table)
        doc.build(elements)
        
        buffer.seek(0)
        return send_file(
            buffer, 
            as_attachment=True, 
            download_name=f"attendance_report_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf", 
            mimetype='application/pdf'
        )

    except Exception as e:
        current_app.logger.exception("PDF Export failed")
        return jsonify({"error": "Export failed"}), 500