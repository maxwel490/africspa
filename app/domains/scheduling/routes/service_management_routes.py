"""Scheduling routes: service management (admin_bp)."""
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import Service, Worker, Salon, db
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.decorators import roles_required
from app.middleware.access_control_middleware import no_services_access
from app.admin import admin_bp


@admin_bp.route('/services', methods=['GET', 'POST'])
@admin_bp.route('/services/<int:service_id>', methods=['POST']) # Handles Edit/Delete
@login_required
@roles_required('admin')
@no_services_access
def manage_services(service_id=None):
    def parse_float_field(field_name, default=0.0):
        raw_value = request.form.get(field_name, None)
        if raw_value is None:
            return float(default)
        text = str(raw_value).strip()
        if text == '':
            return float(default)
        return float(text)

    # 1. Determine Action: Are we Deleting?
    action = (request.args.get('action') or request.form.get('action') or '').strip().lower()
    selected_branch = request.args.get('branch') or request.form.get('branch')
    
    target_service_id = service_id or request.form.get('service_id', type=int)

    is_delete_intent = (
        target_service_id is not None and (
            action == 'delete' or
            (request.method == 'POST' and not request.form.get('name') and not request.form.get('category'))
        )
    )

    if is_delete_intent:
        service = Service.query.filter_by(id=target_service_id, salon_id=current_user.salon_id).first_or_404()
        try:
            db.session.delete(service)
            db.session.commit()
            flash(f"Service '{service.name}' deleted.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Cannot delete this service because it is used in existing appointment records.", "danger")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Service delete error: {e}")
            flash("Error deleting service. Please try again.", "danger")
        return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))

    # 2. Handle Form Submissions (Create or Edit)
    if request.method == 'POST':
        try:
            # If service_id exists, we are editing; otherwise, creating.
            service = db.session.get(Service, service_id) if service_id else Service()
            if service_id and not service:
                flash("Service not found.", "danger")
                return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))
            
            # Set salon_id for new services (required field)
            if not service_id and not service.salon_id:
                if not current_user.salon_id:
                    flash("No salon associated with user. Cannot create service.", "danger")
                    return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))
                service.salon_id = current_user.salon_id
            
            # Capture inputs
            service.name = request.form.get('name', '').strip()
            service.category = request.form.get('category')

            if not service.name:
                flash("Service name is required.", "danger")
                return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))

            if not service.category:
                flash("Service category is required.", "danger")
                return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))

            duplicate_query = Service.query.filter(
                func.lower(Service.name) == service.name.lower(),
                Service.salon_id == current_user.salon_id
            )
            if service_id:
                duplicate_query = duplicate_query.filter(Service.id != service_id)
            if duplicate_query.first():
                flash(f"A service named '{service.name}' already exists in your salon.", "danger")
                return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))

            service.base_price = parse_float_field('base_price', 0.0)
            selected_is_fixed = (request.form.get('is_fixed_base') or 'true').strip().lower() == 'true'
            
            comm_front = parse_float_field('commission_front', 0.0)
            comm_back = parse_float_field('commission_back', 0.0)

            # 3. Apply Business Logic Branching
            if service.category == 'Hair':
                service.is_fixed_base = selected_is_fixed
                # Keeps raw values (can be Rates or Fixed KSh based on JS)
                service.commission_front = comm_front
                service.commission_back = comm_back
            
            elif service.category == 'Special Hair':
                service.is_fixed_base = selected_is_fixed
                # Both are rates (e.g., 0.25)
                service.commission_front = comm_front
                service.commission_back = comm_back
                
            else:
                service.is_fixed_base = selected_is_fixed
                # Non-Hair: comm_front is a rate, back is forced to 0
                service.commission_front = comm_front
                service.commission_back = 0.0

            if not service_id:
                db.session.add(service)
            
            db.session.commit()
            flash(f"Service '{service.name}' saved successfully!", "success")
            
        except ValueError:
            db.session.rollback()
            flash("Error processing service: Ensure all values are numeric.", "danger")
        except IntegrityError:
            db.session.rollback()
            flash("Service could not be saved due to duplicate or invalid data.", "danger")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Service save error: {e}")
            flash("Error processing service. Please try again.", "danger")
            
        return redirect(url_for('admin.manage_services', branch=selected_branch) if selected_branch else url_for('admin.manage_services'))

    # 3. GET: Fetch and display list
    services = Service.query.filter_by(salon_id=current_user.salon_id).order_by(Service.category, Service.name).all()
    
    # Get salon's currency for pricing display
    salon_currency = 'KES'  # Default
    if current_user.salon_id:
        from app.models import Salon
        salon = Salon.query.get(current_user.salon_id)
        if salon and salon.currency:
            salon_currency = salon.currency
    
    return render_template('admin/services.html', services=services, salon_currency=salon_currency)
