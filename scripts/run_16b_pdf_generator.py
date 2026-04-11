import json
import os
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import cm

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
input_path = os.path.join(base_dir, "output", "routes", "neuss_route_sheets_v1.json")
output_dir = os.path.join(base_dir, "output", "installer_packs")
report_path = os.path.join(output_dir, "installer_pack_generation_report.json")

os.makedirs(output_dir, exist_ok=True)

def generate_pdfs():
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    df = pd.DataFrame(data)
    
    unique_routes = df['route_id'].nunique()
    unique_clusters = df['cluster_id'].nunique()
    record_count = len(df)
    
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    normal_style = styles['Normal']
    
    # Custom note style to be smaller
    note_style = ParagraphStyle(
        'NoteStyle',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.gray,
        leading=10
    )
    
    pdfs_generated = 0
    invalid_rows_skipped = 0
    
    groups = df.groupby('route_id')
    
    for route_id, group in groups:
        group = group.sort_values('stop_order')
        
        pdf_path = os.path.join(output_dir, f"installer_pack_{route_id}.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        
        story = []
        
        c_id = group['cluster_id'].iloc[0]
        c_label = group['cluster_label'].iloc[0]
        seg_id = group['segment_id'].iloc[0]
        stop_count = len(group)
        
        story.append(Paragraph(f"D-ESS Installer Route Pack", title_style))
        story.append(Spacer(1, 0.5 * cm))
        
        info_text = f"<b>Route ID:</b> {route_id} &nbsp;&nbsp;&nbsp; <b>Cluster ID:</b> {c_id}<br/>"
        info_text += f"<b>Cluster Label:</b> {c_label}<br/>"
        info_text += f"<b>Segment ID:</b> {seg_id} &nbsp;&nbsp;&nbsp; <b>Total Stops:</b> {stop_count}"
        story.append(Paragraph(info_text, normal_style))
        story.append(Spacer(1, 1 * cm))
        
        table_data = []
        table_data.append(["Stop #", "Street", "House No.", "Class", "Priority", "Action", "Status"])
        
        for idx, row in group.iterrows():
            street = row.get('street', '')
            hn = row.get('house_number', '')
            if pd.isna(hn) or str(hn).strip() == '':
                hn = "N/A"
            if pd.isna(street) or str(street).strip() == '':
                street = "Unnamed Geo."
                
            lead_class = row.get('lead_class', 'N/A')
            priority = row.get('visit_priority', 'N/A')
            action = row.get('recommended_action', 'N/A')
            
            cb_para = Paragraph("[ ] visited<br/>[ ] interested<br/>[ ] no_answer<br/>[ ] not_suitable", note_style)
            street_para = Paragraph(str(street), normal_style)
            action_para = Paragraph(str(action), note_style)
            
            stop_str = str(row['stop_order'])
            
            table_row = [
                stop_str,
                street_para,
                str(hn),
                str(lead_class),
                str(priority),
                action_para,
                cb_para
            ]
            
            table_data.append(table_row)
            
            notes = row.get('notes', '')
            if pd.notna(notes) and str(notes).strip():
                note_p = Paragraph(f"<i>Notes: {notes}</i>", note_style)
                table_data.append(["", note_p, "", "", "", "", ""])
            
        t_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ])
        
        for i, row_data in enumerate(table_data):
            if i > 0 and row_data[0] == "":
                t_style.add('SPAN', (1, i), (-1, i))
                t_style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor("#F9F9F9"))
                
        col_widths = [1.2*cm, 3.5*cm, 2.0*cm, 1.2*cm, 2.0*cm, 3.0*cm, 3.5*cm]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(t_style)
        
        story.append(t)
        doc.build(story)
        pdfs_generated += 1
        
    report = {
        "input_file": input_path,
        "record_count": int(record_count),
        "unique_routes": int(unique_routes),
        "unique_clusters": int(unique_clusters),
        "pdfs_generated": pdfs_generated,
        "invalid_rows_skipped": invalid_rows_skipped,
        "output_dir": output_dir
    }
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
        
    print(f"PDF_GENERATION_COMPLETE")
    print(f"Pdfs Created: {pdfs_generated}")

    # Output exact user request output block format so the system can parse it
    print(f"\nReport:")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    generate_pdfs()
