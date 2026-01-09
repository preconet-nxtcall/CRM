# app/routes/admin_performance.py

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, and_, or_, case
from datetime import datetime, timedelta

from app.models import db, CallHistory, User, Admin, Attendance

bp = Blueprint("admin_performance", __name__, url_prefix="/api/admin")


# ---------------------------
# Helper: Date Range Filter
# ---------------------------
def get_date_range(filter_type):
    now = datetime.utcnow()

    if filter_type == "today":
        start = datetime(now.year, now.month, now.day)
        end = start + timedelta(days=1)

    elif filter_type == "week":
        start = now - timedelta(days=7)
        end = now

    elif filter_type == "month":
        start = now - timedelta(days=30)
        end = now

    else:
        start = datetime(2000, 1, 1)
        end = now

    return start, end


# ---------------------------
# GET /api/admin/performance
# ---------------------------
@bp.route("/performance", methods=["GET"])
@jwt_required()
def performance():
    try:
        admin_id = int(get_jwt_identity())
        admin = Admin.query.get(admin_id)

        if not admin:
            return jsonify({"error": "Unauthorized"}), 401

        # Load filter (start_dt, end_dt)
        filter_type = request.args.get("filter", "today")
        start_dt, end_dt = get_date_range(filter_type)
        
        # User Filter
        user_id_param = request.args.get("user_id", "all")

        # Base user query
        user_query = User.query.filter(User.admin_id == admin_id)
        if user_id_param and user_id_param != "all":
            try:
                user_query = user_query.filter(User.id == int(user_id_param))
            except:
                pass
        
        users = user_query.all()
        users_list = []

        # Helper to check if time is in lunch (13:00 - 14:00)
        def is_lunch_time(dt):
            return dt.hour == 13

        for user in users:
            # 1. Fetch Attendance (to define work sessions)
            # We assume one main session per day for simplicity or take min(check_in) and max(check_out)
            # Filtering by range
            attendances = Attendance.query.filter(
                Attendance.user_id == user.id,
                Attendance.check_in >= start_dt,
                Attendance.check_in < end_dt
            ).all()

            # 2. Fetch Call History
            calls = CallHistory.query.filter(
                CallHistory.user_id == user.id,
                CallHistory.timestamp >= start_dt,
                CallHistory.timestamp < end_dt
            ).order_by(CallHistory.timestamp.asc()).all()

            # Group by Date (YYYY-MM-DD)
            daily_data = {}

            # Process Attendance to get CheckIn/CheckOut per day
            for att in attendances:
                d_str = att.check_in.date().isoformat()
                if d_str not in daily_data:
                    daily_data[d_str] = {"check_in": att.check_in, "check_out": att.check_out, "calls": []}
                else:
                    # Update min check_in and max check_out if multiple records exist
                    if att.check_in < daily_data[d_str]["check_in"]:
                        daily_data[d_str]["check_in"] = att.check_in
                    
                    # Handle check_out selection
                    # If existing is None, keep it None (or update?)
                    # If this one is None (currently working?), keep None?
                    # Let's try to find the latest valid check_out
                    current_co = daily_data[d_str]["check_out"]
                    if att.check_out:
                         if current_co is None or att.check_out > current_co:
                             daily_data[d_str]["check_out"] = att.check_out
            
            # Map calls to days
            for call in calls:
                d_str = call.timestamp.date().isoformat()
                if d_str in daily_data:
                    daily_data[d_str]["calls"].append(call)
                # Note: calls on days without attendance are effectively ignored for "performance" as per rules? 
                # "No performance calculation... Before check-in". 
                # So we only care if there is attendance.

            # Calculate Stats
            total_active_sec = 0.0
            total_inactive_sec = 0.0
            total_work_sec = 0.0
            
            # Keep track of detailed counts for table
            incoming = 0
            outgoing = 0
            missed = 0
            rejected = 0
            total_calls = 0

            for d_str, day_info in daily_data.items():
                c_in = day_info["check_in"]
                c_out = day_info["check_out"]
                
                # If currently working (no check_out), assume NOW (if today)
                if c_out is None:
                    if d_str == datetime.utcnow().date().isoformat():
                        c_out = datetime.utcnow()
                    else:
                        # Forgot to checkout previous day? 
                        # We could ignore, or assume end of day? 
                        # Let's skip calculation or assume 1 hour of work? 
                        # Safe fallback: assume inactive if forgot.
                        continue 

                # Total Work Time = (Out - In) - 1 Hour (Lunch)
                session_dur = (c_out - c_in).total_seconds()
                work_dur = max(0, session_dur - 3600)
                total_work_sec += work_dur

                # GAP CALCULATION
                last_sync_time = c_in
                day_calls = day_info["calls"]
                
                # Add counts
                for c in day_calls:
                    total_calls += 1
                    ct = c.call_type.lower()
                    if ct == 'incoming': incoming += 1
                    elif ct == 'outgoing': outgoing += 1
                    elif ct == 'missed': missed += 1
                    elif ct == 'rejected': rejected += 1

                # Sort calls? They are query ordered, but careful if appended differently
                # They are from sorted query.

                for call in day_calls:
                    curr_time = call.timestamp
                    
                    # 1. Check bounds
                    if curr_time < c_in: continue # Before check-in
                    if curr_time > c_out: continue # After check-out
                    
                    # 2. Check Lunch (13:00 - 14:00)
                    # Simple hour check
                    if is_lunch_time(curr_time):
                        # Inside lunch: Ignore gap, update last sync
                        last_sync_time = curr_time
                        continue
                    
                    # 3. Calculate Gap
                    # Ensure last_sync_time is also not in lunch? 
                    # If last_sync was 12:50 and curr is 14:10. Gap is 1h 20m.
                    # Lunch is 13-14. 
                    # Pure Gap = 80 mins. 
                    # Subtract Lunch overlap?
                    # The instruction says: "If sync event occurs inside lunch... DO NOT UPDATE ACTIVITY".
                    # It implies gaps spanning over lunch might be tricky.
                    # "No performance calculations are allowed during 1 PM - 2 PM".
                    # Let's strictly block 1-2.
                    # If last_sync < 13:00 and curr > 14:00.
                    # We should subtract 60 mins from gap?
                    
                    # Simplified logic based on "Classify each gap... gap = curr - last"
                    # If strictly adhering to "No calc during lunch", we can clamp timestamps.
                    
                    # Workable approach:
                    # Calculate raw gap.
                    # If gap spans lunch, subtract overlap.
                    
                    raw_gap = (curr_time - last_sync_time).total_seconds()
                    
                    # Adjust for lunch overlap
                    # Lunch range for this day
                    lunch_start = c_in.replace(hour=13, minute=0, second=0, microsecond=0)
                    lunch_end = c_in.replace(hour=14, minute=0, second=0, microsecond=0)
                    
                    # Intersect (last_sync, curr_time) with (lunch_start, lunch_end)
                    overlap_start = max(last_sync_time, lunch_start)
                    overlap_end = min(curr_time, lunch_end)
                    overlap = max(0, (overlap_end - overlap_start).total_seconds())
                    
                    effective_gap = max(0, raw_gap - overlap)
                    
                    # If last_sync was inside lunch, overlap handles it (overlap start = last_sync)
                    # If curr_time inside lunch, overlap handles it (overlap end = curr_time)
                    
                    if effective_gap <= 600: # 10 mins * 60
                         total_active_sec += effective_gap
                    else:
                         total_inactive_sec += effective_gap
                         
                    last_sync_time = curr_time

                # Add final gap (Call -> Checkout)? 
                # "From check-in to check-out"
                # The prompt says: "Classify each gap between call syncs". 
                # Does it include gap from last call to check-out? 
                # Usually yes for "Continuous calculation".
                # "gap = current_sync_time - last_sync_time". 
                # If we consider check-out as a sync event?
                # "For every call sync event".
                # It doesn't explicitly say check-out is a sync event for gap calc, 
                # BUT "Define total working time... Activity Ratio = Active / Total".
                # If we don't count the end, we miss a lot.
                # Let's treat Check-Out as the final "Sync Event".
                
                # Check-out Calc
                final_gap_raw = (c_out - last_sync_time).total_seconds()
                
                lunch_start = c_in.replace(hour=13, minute=0, second=0, microsecond=0)
                lunch_end = c_in.replace(hour=14, minute=0, second=0, microsecond=0)
                
                overlap_start = max(last_sync_time, lunch_start)
                overlap_end = min(c_out, lunch_end)
                overlap = max(0, (overlap_end - overlap_start).total_seconds())
                
                final_gap = max(0, final_gap_raw - overlap)
                
                if final_gap <= 600:
                    total_active_sec += final_gap
                else:
                    total_inactive_sec += final_gap


            # 4. Activity Ratio & Status
            # Safety: avoid division by zero
            if total_work_sec > 0:
                ratio = total_active_sec / total_work_sec
            else:
                ratio = 0.0
            
            # Cap ratio at 1.0 (though logic shouldn't exceed it unless overlap bug)
            ratio = min(ratio, 1.0)
            
            percentage = round(ratio * 100, 1)

            if ratio >= 0.75:
                status = "Excellent"
            elif ratio >= 0.50:
                status = "Moderate"
            else:
                # If work time exists but low active -> Poor
                # If no work time -> Inactive?
                # Prompt: "If user does not sync at all, active_time = 0 and performance becomes 'Inactive'"
                # "Below 0.50 Inactive / Poor"
                if total_work_sec == 0:
                     status = "Inactive"
                else:
                     status = "Poor"

            # Determine "Last Active Day" for the Details Modal
            # Instead of overall sums, we show the stats for the most recent day user worked.
            last_day_stats = {
                "active": 0, "inactive": 0, "work": 0, "in": None, "out": None
            }
            
            if daily_data:
                # Find max date
                last_date_str = max(daily_data.keys())
                day_info = daily_data[last_date_str]
                
                # Re-calc stats for just this day
                # (We did this in the loop above but aggregated it. We need to isolate it or extract it)
                # Since the loop above summed things up and didn't store per-day breakdown in 'daily_data'
                # cleanly for simple retrieval without re-running gap logic (gap logic was inside the loop),
                # we might need to adjust the loop or repeat the logic for this one day.
                
                # OPTION: The loop above iterates daily_data. We can just capture the values for the last day.
                # But the loop logic is complex (gaps). 
                
                # Let's rebuild the gap logic for the 'last_day' specifically to be safe and accurate.
                c_in = day_info["check_in"]
                c_out = day_info["check_out"]
                
                # Handle 'current/now' check-out if None
                if c_out is None and last_date_str == datetime.utcnow().date().isoformat():
                     c_out = datetime.utcnow()
                
                if c_out:
                    # CLAMP DATA TO "THIS DAY" (Start Date)
                    # If user checked out days later, we only count the work time for the check-in day
                    # to match the user perception of "Today's Work Time".
                    
                    day_end = c_in.replace(hour=23, minute=59, second=59, microsecond=999999)
                    eff_c_out = min(c_out, day_end)

                    # Work Time for this specific day
                    session_dur = (eff_c_out - c_in).total_seconds()
                    
                    # Gap calc for this day
                    l_active = 0
                    l_inactive = 0
                    
                    last_sync = c_in
                    day_calls = day_info["calls"]
                    
                    def is_lunch(dt): return dt.hour == 13
                    
                    for call in day_calls:
                        ct = call.timestamp
                        
                        # Safety Check: Ignore calls outside session (clamped)
                        if ct < c_in or ct > eff_c_out: 
                            continue

                        # If CALL is during lunch, update last_sync but don't count gap
                        if is_lunch(ct):
                            last_sync = ct
                            continue
                        
                        # Calculate Gap from Last Sync to Current Call
                        raw_gap = (ct - last_sync).total_seconds()
                        
                        # Determine overlapping lunch window for this GAP
                        current_lunch_start = last_sync.replace(hour=13, minute=0, second=0, microsecond=0)
                        current_lunch_end = last_sync.replace(hour=14, minute=0, second=0, microsecond=0)
                        
                        # Calculate overlap
                        ov_s = max(last_sync, current_lunch_start)
                        ov_e = min(ct, current_lunch_end)
                        overlap = max(0, (ov_e - ov_s).total_seconds())
                        
                        # Efficient Gap (Active) = Raw Gap - Lunch Overlap
                        eff_gap = max(0, raw_gap - overlap)
                        
                        if eff_gap <= 600: # 10 mins
                            l_active += eff_gap
                        else:
                            l_inactive += eff_gap
                            
                        last_sync = ct
                        
                    # Final gap (Last Call -> Check Out)
                    raw_gap = (eff_c_out - last_sync).total_seconds()
                    
                    current_lunch_start = last_sync.replace(hour=13, minute=0, second=0, microsecond=0)
                    current_lunch_end = last_sync.replace(hour=14, minute=0, second=0, microsecond=0)
                    
                    ov_s = max(last_sync, current_lunch_start)
                    ov_e = min(eff_c_out, current_lunch_end)
                    overlap = max(0, (ov_e - ov_s).total_seconds())
                    
                    eff_gap = max(0, raw_gap - overlap)
                    
                    if eff_gap <= 600:
                        l_active += eff_gap
                    else:
                        l_inactive += eff_gap
                    
                    # Total work time (Session - Lunch Overlap of Session)
                    l_start = c_in.replace(hour=13, minute=0, second=0, microsecond=0)
                    l_end = c_in.replace(hour=14, minute=0, second=0, microsecond=0)
                    
                    ov_s = max(c_in, l_start)
                    ov_e = min(eff_c_out, l_end)
                    lunch_taken = max(0, (ov_e - ov_s).total_seconds())
                    
                    last_day_stats["work"] = max(0, session_dur - lunch_taken)
                    last_day_stats["active"] = l_active
                    last_day_stats["inactive"] = l_inactive
                    last_day_stats["in"] = c_in
                    # Show actual check out time in UI (so user knows they worked late?)
                    # OR show clamped? User said "only this day".
                    # Screenshot shows 07:44 PM.
                    # If I show clamped 11:59 PM, they might be confused.
                    # I will stick to displaying the REAL check out, but calculating stats on clamped.
                    # BUT wait, the backend sends formatted time.
                    # If I use c_out (real), it shows 7pm (next day).
                    # Ideally I show proper Date if diff day.
                    # But for now, let's keep 'out' as c_out strictly for display purposes in the modal header?
                    # The screenshot shows the metrics being 80h.
                    # This change fixes the METRICS.
                    last_day_stats["out"] = c_out

            def fmt_hms(seconds):
                if not seconds: return "0s"
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = int(seconds % 60)
                parts = []
                if h: parts.append(f"{h}h")
                if m: parts.append(f"{m}m")
                if s: parts.append(f"{s}s")
                return " ".join(parts)

            users_list.append({
                "user_id": user.id,
                "user_name": user.name,
                "total_calls": total_calls,
                "incoming": incoming,
                "outgoing": outgoing,
                "missed": missed,
                "rejected": rejected,
                "total_work_sec": total_work_sec,
                "active_sec": total_active_sec,
                "inactive_sec": total_inactive_sec,
                "score": percentage, # Overall Score
                "status": status,    # Overall Status
                "details": {
                    "active_time": fmt_hms(last_day_stats['active']),
                    "inactive_time": fmt_hms(last_day_stats['inactive']),
                    "work_time": fmt_hms(last_day_stats['work']),
                    "check_in": last_day_stats['in'].strftime("%I:%M %p") if last_day_stats['in'] else "-",
                    "check_out": last_day_stats['out'].strftime("%I:%M %p") if last_day_stats['out'] else "-"
                }
            })

        # Sort by Score (Ratio)
        sort_order = request.args.get("sort", "desc")
        reverse = (sort_order == "desc")
        users_list.sort(key=lambda x: x["score"], reverse=reverse)

        # Prepare response
        labels = [u["user_name"] for u in users_list]
        values = [u["score"] for u in users_list] # This is now %
        user_ids = [u["user_id"] for u in users_list]
        
        # Extra arrays for table rendering
        statuses = [u["status"] for u in users_list]
        details = [u["details"] for u in users_list]

        return jsonify({
            "labels": labels,
            "values": values,
            "user_ids": user_ids,
            "statuses": statuses,
            "details": details,
            # Maintain backward compat for other fields if frontend uses them sparingly
            "incoming": [u["incoming"] for u in users_list],
            "outgoing": [u["outgoing"] for u in users_list], 
            "total_calls": [u["total_calls"] for u in users_list]
        }), 200

    except Exception as e:
        print(f"Performance error: {e}") # Log to console
        return jsonify({"error": str(e)}), 400
