# AfricSpa Multi-Tenant Architecture

## Overview

AfricSpa is a fully multi-tenant SaaS platform that provides complete data isolation between different salon businesses while allowing seamless data sharing within each salon's branches.

## Architecture Principles

### 🏢 **Salon-Level Isolation**
- **Complete Data Separation**: Each salon operates as an independent tenant
- **No Cross-Salon Data Leakage**: Salon A cannot access Salon B's data under any circumstances
- **Independent Business Logic**: Each salon has its own clients, appointments, products, and financial data

### 🏪 **Branch-Level Sharing**
- **Shared Client Database**: Clients are shared across all branches within the same salon
- **Unified Business Operations**: A client can visit any branch of the same salon and their data is accessible
- **Branch-Specific Filtering**: Users can view data for their specific branch or all branches (based on role)

## Data Model Design

### Core Multi-Tenant Fields

Every business-critical model includes these multi-tenant fields:

```python
# Multi-tenant fields
salon_id = db.Column(db.Integer, db.ForeignKey('salons.id'), nullable=False)
branch = db.Column(db.String(20), nullable=False, index=True)  # For branch-level operations
```

### Models with Multi-Tenant Isolation

1. **Client Model**
   - `salon_id`: Ensures clients belong to specific salon
   - `branch`: Indicates preferred/primary branch
   - Email uniqueness enforced per salon: `UniqueConstraint('email', 'salon_id')`

2. **Worker Model**
   - `salon_id`: Workers belong to specific salon
   - `branch`: Worker's assigned branch
   - Role-based access control

3. **Appointment Model**
   - `salon_id`: Appointments belong to specific salon
   - `branch`: Where appointment takes place
   - Complete isolation between salons

4. **Product Model**
   - `salon_id`: Inventory is salon-specific
   - `branch`: Product location/stock
   - Shared across salon branches

5. **Branch Model**
   - `salon_id`: Branches belong to specific salon
   - Hierarchical structure: Salon → Branches

## Access Control Patterns

### Role-Based Data Access

| Role | Salon Access | Branch Access | Capabilities |
|------|-------------|--------------|--------------|
| **Super Admin** | All Salons | All Branches | System-wide management |
| **Admin** | Own Salon | All Branches | Full salon management |
| **Accountant** | Own Salon | All Branches | Financial operations |
| **Salonist** | Own Salon | Own Branch | Personal schedule & services |

### Data Access Validation

```python
# Example: Client access validation
def can_be_accessed_by(self, user):
    if not user.is_authenticated:
        return False
    
    # Super Admin can access all clients
    if user.role == 'superadmin':
        return True
    
    # Users can only access clients from their own salon
    return self.salon_id == user.salon_id
```

## Query Patterns

### Tenant-Isolated Queries

```python
# Get current salon's clients
def get_salon_clients(include_all_branches=True):
    salon_id = get_current_salon_id()
    query = Client.query.filter_by(salon_id=salon_id)
    
    if not include_all_branches:
        current_branch = get_current_branch()
        if current_branch:
            query = query.filter_by(branch=current_branch)
    
    return query.all()
```

### Automatic Tenant Filtering

```python
# Decorator for automatic tenant isolation
@tenant_data_isolation
def manage_clients():
    # All queries automatically filtered by current_user.salon_id
    clients = Client.query.all()  # Automatically scoped to current salon
```

## Security Features

### 🔐 **Data Isolation Guarantees**

1. **Database Level**: Foreign key constraints prevent cross-salon relationships
2. **Application Level**: All queries automatically filtered by `salon_id`
3. **Validation Level**: Access control checks on every data operation
4. **Session Level**: User context always includes salon information

### 🛡️ **Access Control Mechanisms**

1. **Authentication**: Users must be logged in
2. **Authorization**: Role-based permissions
3. **Tenant Validation**: Every data access validates salon membership
4. **Branch Filtering**: Optional branch-level data scoping

## Implementation Examples

### Creating a New Client

```python
def create_client(client_data):
    # Automatically assign current user's salon
    client_data['salon_id'] = current_user.salon_id
    
    # Validate email uniqueness within salon
    if not Client.validate_email_uniqueness(
        client_data['email'], 
        client_data['salon_id']
    ):
        raise ValueError("Email already exists in this salon")
    
    client = Client(**client_data)
    db.session.add(client)
    db.session.commit()
```

### Cross-Branch Client Access

```python
# Salon Admin can see all clients across all branches
@branch_level_access
def view_all_clients():
    if current_user.role in ['admin', 'accountant']:
        return get_salon_clients(include_all_branches=True)
    else:
        # Salonist sees only their branch clients
        return get_salon_clients(include_all_branches=False)
```

## Testing & Validation

### Automated Tests

The system includes comprehensive tests to verify:

1. **Data Isolation**: No cross-salon data leakage
2. **Access Control**: Proper role-based permissions
3. **Branch Sharing**: Correct data sharing within salon
4. **Email Uniqueness**: Proper validation per salon

### Test Results

```
✅ Salon-level data isolation: WORKING
✅ Branch-level data sharing: WORKING  
✅ No cross-salon data leakage: CONFIRMED
✅ Email uniqueness per salon: WORKING
```

## Business Logic

### Client Management

- **Salon A Clients**: Completely isolated from Salon B
- **Branch Access**: Client can visit any branch within their salon
- **Data Consistency**: Client data is consistent across all salon branches

### Appointment Booking

- **Cross-Branch**: Clients can book appointments at any branch
- **Staff Assignment**: Workers can only see appointments from their branch/salon
- **Financial Tracking**: Revenue tracked per salon, with branch breakdowns

### Inventory Management

- **Shared Inventory**: Products available across all salon branches
- **Branch Stock**: Stock levels tracked per branch
- **Salon-Wide Reporting**: Consolidated inventory reports for salon management

## Performance Considerations

### Database Indexing

- `salon_id` indexed on all multi-tenant tables
- Composite indexes for frequent query patterns
- Optimized queries for tenant filtering

### Caching Strategy

- Tenant-specific cache keys
- Automatic cache invalidation per salon
- Branch-level cache segmentation

## Deployment Notes

### Environment Setup

1. **Database**: Proper foreign key constraints
2. **Application**: Tenant-aware middleware
3. **Security**: Role-based access control
4. **Monitoring**: Tenant-specific metrics

### Scalability

- **Horizontal Scaling**: Multiple salons per database instance
- **Vertical Scaling**: Branch expansion within salons
- **Performance**: Optimized for multi-tenant workloads

## Conclusion

The BeautySpace multi-tenant architecture provides:

✅ **Complete Data Isolation** between different salon businesses
✅ **Seamless Branch Sharing** within each salon
✅ **Role-Based Access Control** for all user types
✅ **Scalable Design** for growing SaaS platform
✅ **Security-First Approach** with comprehensive validation

This ensures that each salon operates as an independent business while benefiting from shared infrastructure and branch-level collaboration capabilities.
