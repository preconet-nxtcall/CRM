from app import create_app
from app.models import db, Lead, User, Admin, now
from app.services.lead_service import LeadService
from app.services.assignment_service import AssignmentService
import uuid

app = create_app()

with app.app_context():
    print("Running Verification...")
    
    # 1. Setup Dummy Admin & Agent
    admin = Admin.query.first()
    if not admin:
        print("No Admin found. Skipping.")
        exit()
        
    print(f"Using Admin: {admin.email} (ID: {admin.id})")
    
    agent = User.query.filter_by(admin_id=admin.id).first()
    if not agent:
        print("No Agent found. Skipping.")
        exit()
        
    print(f"Using Agent: {agent.name} (ID: {agent.id})")
    
    # 2. Test Ingestion
    print("\n[TEST] Ingesting Lead...")
    lead_id = f"TEST_{uuid.uuid4().hex[:8]}"
    data = {
        "name": "Test Lead",
        "phone": "9999999999",
        "sub_source": "Verification Script",
        "lead_identifier": lead_id
    }
    
    lead = LeadService.ingest_lead(admin.id, "Script", data)
    
    if lead:
        print(f"✅ Lead Created: ID {lead.id}, Status: {lead.status}")
        print(f"   Lead Identifier: {lead.lead_identifier}")
        print(f"   Sub Source: {lead.sub_source}")
    else:
        print("❌ Lead Ingestion Failed")
        exit()
        
    # 3. Verify Assignment
    print("\n[TEST] Verifying Assignment...")
    if lead.assigned_to:
        print(f"✅ Assigned to: {lead.assigned_agent_name} (ID: {lead.assigned_to})")
        print(f"✅ Assignment Time: {lead.assignment_time}")
    else:
        print("❌ Lead Not Assigned")
        
    # 4. Test Deduplication
    print("\n[TEST] Verifying Deduplication...")
    dup_lead = LeadService.ingest_lead(admin.id, "Script", data)
    if dup_lead.id == lead.id:
        print(f"✅ Deduplication Worked. Returned Lead ID {dup_lead.id}")
    else:
        print(f"❌ Deduplication Failed. Created new ID {dup_lead.id}")
        
    # 5. Test Status Update (Logic check)
    print("\n[TEST] Updating Status...")
    lead.status = "Contacted"
    lead.updated_at = now()
    db.session.commit()
    print(f"✅ Status Updated to: {lead.status}")
    
    # Check Analytics Calculation (Response Time)
    updated_lead = Lead.query.get(lead.id)
    diff = updated_lead.updated_at - updated_lead.assignment_time
    print(f"✅ Measured Response Time: {diff.total_seconds()} seconds")
    
    print("\nVERIFICATION COMPLETE")
