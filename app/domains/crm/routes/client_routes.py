"""CRM routes: client and specialty management (accountant_bp)."""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import current_user, login_required
from app.models import Client, Worker, Service, db
from app.decorators import roles_required
from app.accountant import accountant_bp
from sqlalchemy import or_


@accountant_bp.route('/add-client', methods=['GET', 'POST'])
@login_required
@roles_required('accountant')
def add_client():  # This name MUST match 'add_client' used in url_for
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        # Clients are global - not tied to specific branch
        branch = current_user.branch  # Still track which branch registered them

        try:
            new_client = Client(
                full_name=full_name,
                phone=phone,
                branch=branch  # Track registration branch, but client can visit any branch
            )
            db.session.add(new_client)
            db.session.commit()
            flash(f"Client {full_name} registered successfully! (Global client - can visit any branch)", "success")
            return redirect(url_for('accountant.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash("Error: Phone number might already be registered.", "danger")

    return render_template('accountant/add_client.html')


@accountant_bp.route('/api/search-clients')
@login_required
@roles_required('accountant')
def search_clients():
    """API endpoint for client search with Select2 - Global clients"""
    query = request.args.get('q', '')
    
    clients = Client.query.filter(
        or_(
            Client.full_name.ilike(f'%{query}%'),
            Client.phone.ilike(f'%{query}%')
        )
    ).limit(10).all()
    
    results = []
    for client in clients:
        results.append({
            'id': client.id,
            'text': f"{client.full_name} - {client.phone}",
            'full_name': client.full_name,
            'phone': client.phone
        })
    
    return jsonify({'results': results})


@accountant_bp.route('/api/specialties')
@login_required
@roles_required('accountant')
def get_specialties():
    """API endpoint to get existing specialties for Select2"""
    try:
        # Get unique specialties from workers table for current branch
        specialties = db.session.query(Worker.specialty)\
            .filter(Worker.specialty.isnot(None))\
            .filter(Worker.specialty != '')\
            .filter(Worker.branch == current_user.branch)\
            .distinct()\
            .all()
        
        # Format for Select2
        results = [{'id': spec[0], 'text': spec[0]} for spec in specialties if spec[0]]
        
        return jsonify({
            'results': results,
            'pagination': {'more': False}
        })
    except Exception as e:
        current_app.logger.error(f"Error fetching specialties: {e}")
        return jsonify({'results': []}), 500


@accountant_bp.route('/api/specialties', methods=['POST'])
@login_required
@roles_required('accountant')
def add_specialty():
    """API endpoint to add a new specialty (for Select2 tagging)"""
    try:
        data = request.get_json()
        specialty_name = data.get('text', '').strip()
        
        if not specialty_name:
            return jsonify({'error': 'Specialty name is required'}), 400
        
        # Check if specialty already exists in current branch
        existing = Worker.query.filter_by(specialty=specialty_name, branch=current_user.branch).first()
        if existing:
            return jsonify({
                'id': specialty_name,
                'text': specialty_name
            })
        
        # Return the new specialty (it will be created when a worker is actually added)
        return jsonify({
            'id': specialty_name,
            'text': specialty_name
        })
        
    except Exception as e:
        current_app.logger.error(f"Error adding specialty: {e}")
        return jsonify({'error': 'Failed to add specialty'}), 500